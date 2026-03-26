import logging
from itertools import combinations

import numpy as np
import pandas as pd
from thefuzz import fuzz

from ..geo import haversine_m

log = logging.getLogger(__name__)

PROXIMITY_THRESHOLD_M = 500
NAME_SIMILARITY_THRESHOLD = 70


def merge_registries(source_dfs):
    all_dams = []
    for source_name, df in source_dfs.items():
        if df is None or len(df) == 0:
            continue
        df = df.copy()
        df["_source"] = source_name
        all_dams.append(df)

    if not all_dams:
        log.error("No dam data to merge")
        return pd.DataFrame()

    combined = pd.concat(all_dams, ignore_index=True)
    combined = combined.dropna(subset=["lat", "lon"])
    log.info(f"Total records before dedup: {len(combined)}")

    clusters = _cluster_by_proximity(combined, PROXIMITY_THRESHOLD_M)
    log.info(f"Found {len(clusters)} unique dam clusters")

    merged_dams = []
    for i, cluster in enumerate(clusters):
        merged = _merge_cluster(cluster, dam_id=f"MAR-{i + 1:03d}")
        merged_dams.append(merged)

    result = pd.DataFrame(merged_dams)
    result = result.sort_values("name").reset_index(drop=True)

    for i, _ in result.iterrows():
        result.at[i, "id"] = f"MAR-{i + 1:03d}"

    log.info(f"Merged registry: {len(result)} unique dams")
    return result


def _cluster_by_proximity(df, threshold_m):
    records = df.to_dict("records")
    n = len(records)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    lats = np.array([r["lat"] for r in records])
    lons = np.array([r["lon"] for r in records])

    for i in range(n):
        if i % 500 == 0 and i > 0:
            log.info(f"Clustering progress: {i}/{n}")
        for j in range(i + 1, n):
            if abs(lats[i] - lats[j]) > 0.05:
                continue
            if abs(lons[i] - lons[j]) > 0.05:
                continue
            dist = haversine_m(lats[i], lons[i], lats[j], lons[j])
            if dist <= threshold_m:
                union(i, j)
            elif dist <= threshold_m * 3:
                name_i = records[i].get("name", "")
                name_j = records[j].get("name", "")
                if name_i and name_j and _fuzzy_match(name_i, name_j):
                    union(i, j)

    clusters_dict = {}
    for i in range(n):
        root = find(i)
        clusters_dict.setdefault(root, []).append(records[i])

    return list(clusters_dict.values())


def _fuzzy_match(name1, name2):
    if not name1 or not name2:
        return False
    name1 = _normalize_name(name1)
    name2 = _normalize_name(name2)
    if not name1 or not name2:
        return False
    ratio = fuzz.token_sort_ratio(name1, name2)
    return ratio >= NAME_SIMILARITY_THRESHOLD


def _normalize_name(name):
    if not isinstance(name, str):
        return ""
    name = name.strip().lower()
    for prefix in ["barrage ", "barrage d'", "barrage de ", "barrage du ",
                    "barrage el ", "barrage al ", "dam ", "sdd ", "reservoir "]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name.strip()


def _merge_cluster(records, dam_id):
    names = set()
    sources = set()
    lats, lons = [], []
    heights, capacities, areas, elevations = [], [], [], []
    years, purposes = [], []

    for r in records:
        sources.add(r.get("_source", r.get("source", "")))

        name = r.get("name", "")
        if name and name.lower() not in ("", "nan", "none", "unknown"):
            names.add(name.strip())

        if r.get("lat") is not None:
            lats.append(r["lat"])
        if r.get("lon") is not None:
            lons.append(r["lon"])
        if r.get("height_m") is not None:
            heights.append(r["height_m"])
        if r.get("capacity_mcm") is not None:
            capacities.append(r["capacity_mcm"])
        if r.get("surface_area_km2") is not None:
            areas.append(r["surface_area_km2"])
        if r.get("elevation_m") is not None:
            elevations.append(r["elevation_m"])
        if r.get("year_built") is not None:
            years.append(r["year_built"])
        if r.get("purpose") and str(r["purpose"]).strip():
            purposes.append(str(r["purpose"]).strip())

    primary_name = _pick_best_name(names) if names else "Unknown"

    return {
        "id": dam_id,
        "name": primary_name,
        "names_alt": sorted(names) if names else [],
        "sources": sorted(sources),
        "lat": np.mean(lats) if lats else None,
        "lon": np.mean(lons) if lons else None,
        "height_m": max(heights) if heights else None,
        "capacity_mcm": max(capacities) if capacities else None,
        "surface_area_km2": max(areas) if areas else None,
        "elevation_db_m": np.mean(elevations) if elevations else None,
        "year_built": min(years) if years else None,
        "purpose": list(set(purposes)) if purposes else [],
        "status": "operational",
        "num_sources": len(sources),
    }


def _pick_best_name(names):
    if not names:
        return "Unknown"
    if len(names) == 1:
        return list(names)[0]
    scored = []
    for name in names:
        score = 0
        if any(c.isascii() for c in name):
            score += 1
        if len(name) > 3:
            score += 1
        if not name.startswith("Barrage"):
            score += 1
        score += len(name) / 100
        scored.append((score, name))
    scored.sort(reverse=True)
    return scored[0][1]
