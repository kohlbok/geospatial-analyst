import logging
import math

import numpy as np

from ..config import load_config
from ..geo import haversine_m

log = logging.getLogger(__name__)


def _clean_float(val):
    if val is None:
        return None
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (ValueError, TypeError):
        return None


def _coord_missing(dam):
    lat = dam.get("lat")
    lon = dam.get("lon")
    if lat is None or lon is None:
        return True
    try:
        if math.isnan(float(lat)) or math.isnan(float(lon)):
            return True
    except (ValueError, TypeError):
        return True
    return False


def merge_sources(staged_sources, threshold_m=500):
    config = load_config()
    country_code = config.get("country_code", config.get("country", "DAM")[:3].upper())

    all_records = []
    for source_name, records in staged_sources.items():
        for r in records:
            r["_source"] = source_name
            all_records.append(r)

    with_coords = [r for r in all_records if not _coord_missing(r)]
    without_coords = [r for r in all_records if _coord_missing(r)]

    log.info(f"Total records: {len(all_records)} ({len(with_coords)} with coords, {len(without_coords)} without)")

    clusters = _cluster_by_proximity(with_coords, threshold_m)
    log.info(f"Formed {len(clusters)} clusters from {len(with_coords)} records")

    dams = []
    for cluster in clusters:
        dam = _merge_cluster(cluster)
        dams.append(dam)

    dams.sort(key=lambda d: d.get("name", ""))
    for i, dam in enumerate(dams):
        dam["id"] = f"{country_code}-{i + 1:03d}"

    with_height = sum(1 for d in dams if d.get("height_m") is not None)
    with_cap = sum(1 for d in dams if d.get("capacity_mcm") is not None)

    stats = {
        "total_records": len(all_records),
        "records_with_coords": len(with_coords),
        "records_without_coords": len(without_coords),
        "clusters_formed": len(clusters),
        "dams_merged": len(dams),
        "with_height": with_height,
        "with_capacity": with_cap,
    }

    log.info(f"Merged: {len(dams)} dams, {with_height} with height, {with_cap} with capacity")

    return {
        "dams": dams,
        "edge_cases": without_coords,
        "stats": stats,
    }


def _cluster_by_proximity(records, threshold_m):
    n = len(records)
    parent = list(range(n))
    rank = [0] * n

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1

    lats = np.array([float(r["lat"]) for r in records])
    lons = np.array([float(r["lon"]) for r in records])

    degree_threshold = threshold_m / 111_000

    for i in range(n):
        if i % 500 == 0 and i > 0:
            log.info(f"Clustering progress: {i}/{n}")
        for j in range(i + 1, n):
            if abs(lats[i] - lats[j]) > degree_threshold:
                continue
            if abs(lons[i] - lons[j]) > degree_threshold:
                continue
            dist = haversine_m(lats[i], lons[i], lats[j], lons[j])
            if dist <= threshold_m:
                union(i, j)

    groups = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(records[i])

    return list(groups.values())


def _merge_cluster(records):
    names = set()
    sources = set()
    statuses = set()
    regions = set()
    lats, lons = [], []
    heights, capacities, areas, elevations = [], [], [], []
    grid_distances = []
    years = []
    purposes = set()
    rivers, basins = set(), set()

    for r in records:
        sources.add(r.get("_source", r.get("source", "")))

        name = r.get("name", "")
        if name and str(name).lower() not in ("", "nan", "none", "unknown"):
            names.add(str(name).strip())

        status = r.get("status")
        if status and str(status).lower() not in ("", "nan", "none"):
            statuses.add(str(status).strip())

        region = r.get("region")
        if region and str(region).lower() not in ("", "nan", "none"):
            regions.add(str(region).strip())

        lat = _clean_float(r.get("lat"))
        lon = _clean_float(r.get("lon"))
        if lat is not None:
            lats.append(lat)
        if lon is not None:
            lons.append(lon)
        h = _clean_float(r.get("height_m"))
        if h is not None:
            heights.append(h)
        c = _clean_float(r.get("capacity_mcm"))
        if c is not None:
            capacities.append(c)
        a = _clean_float(r.get("surface_area_km2"))
        if a is not None:
            areas.append(a)
        e = _clean_float(r.get("elevation_m"))
        if e is not None:
            elevations.append(e)
        g = _clean_float(r.get("grid_distance_km"))
        if g is not None:
            grid_distances.append(g)
        y = _clean_float(r.get("year_built"))
        if y is not None:
            years.append(int(y))

        purpose = r.get("purpose")
        if isinstance(purpose, list):
            purposes.update(p for p in purpose if p)
        elif purpose and str(purpose).strip():
            purposes.add(str(purpose).strip())

        river = r.get("river")
        if river and str(river).lower() not in ("", "nan", "none"):
            rivers.add(str(river).strip())
        basin = r.get("basin")
        if basin and str(basin).lower() not in ("", "nan", "none"):
            basins.add(str(basin).strip())

    STANDARD_FIELDS = {
        "name", "alt_names", "lat", "lon", "height_m", "capacity_mcm",
        "surface_area_km2", "elevation_m", "year_built", "river", "basin",
        "purpose", "sources", "status", "_source", "source",
        "region", "grid_distance_km", "nearest_substation", "substation_voltage_kv",
        "id",
    }

    extra = {}
    for r in records:
        for k, v in r.items():
            if k in STANDARD_FIELDS or k in extra:
                continue
            if v is not None and str(v).lower() not in ("", "nan", "none"):
                extra[k] = v

    dam = {
        "name": max(names, key=len) if names else "Unnamed",
        "alt_names": sorted(names) if names else [],
        "lat": float(np.mean(lats)) if lats else None,
        "lon": float(np.mean(lons)) if lons else None,
        "height_m": max(heights) if heights else None,
        "capacity_mcm": max(capacities) if capacities else None,
        "surface_area_km2": max(areas) if areas else None,
        "elevation_m": float(np.mean(elevations)) if elevations else None,
        "grid_distance_km": min(grid_distances) if grid_distances else None,
        "year_built": min(years) if years else None,
        "river": sorted(rivers)[0] if rivers else None,
        "basin": sorted(basins)[0] if basins else None,
        "region": sorted(regions)[0] if regions else None,
        "purpose": sorted(purposes) if purposes else [],
        "sources": sorted(sources),
        "status": sorted(statuses)[0] if statuses else None,
    }
    dam.update(extra)
    return dam


