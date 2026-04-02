import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import overpy

from ..geo import haversine_km

log = logging.getLogger(__name__)

OVERPASS_DELAY = 5
MAX_RETRIES = 5


MIN_VOLTAGE_KV = 60


def _parse_max_voltage_kv(voltage_str):
    if not voltage_str or voltage_str in ("unknown", "none", "?"):
        return 0
    parts = str(voltage_str).replace(",", ";").split(";")
    max_v = 0
    for p in parts:
        try:
            v = int(p.strip())
            if v > max_v:
                max_v = v
        except ValueError:
            continue
    return max_v / 1000


def nearest_substation(lat, lon, radius_km=50):
    api = overpy.Overpass()
    query = f"""
    [out:json][timeout:30];
    (
      node["power"="substation"](around:{radius_km * 1000},{lat},{lon});
      way["power"="substation"](around:{radius_km * 1000},{lat},{lon});
    );
    out center tags;
    """
    for attempt in range(MAX_RETRIES):
        try:
            result = api.query(query)

            candidates = []
            for node in result.nodes:
                d = haversine_km(lat, lon, float(node.lat), float(node.lon))
                voltage_kv = _parse_max_voltage_kv(node.tags.get("voltage"))
                candidates.append((d, node.tags.get("name", "unnamed"), voltage_kv))
            for way in result.ways:
                d = haversine_km(lat, lon, float(way.center_lat), float(way.center_lon))
                voltage_kv = _parse_max_voltage_kv(way.tags.get("voltage"))
                candidates.append((d, way.tags.get("name", "unnamed"), voltage_kv))

            hv = [c for c in candidates if c[2] >= MIN_VOLTAGE_KV]
            best = min(hv, key=lambda c: c[0]) if hv else (min(candidates, key=lambda c: c[0]) if candidates else None)

            if best is None:
                return {"grid_distance_km": None, "nearest_substation": None, "substation_voltage_kv": None}

            return {
                "grid_distance_km": round(best[0], 1),
                "nearest_substation": best[1],
                "substation_voltage_kv": best[2] if best[2] > 0 else None,
            }
        except Exception as e:
            wait = OVERPASS_DELAY * (attempt + 1) * 2
            log.warning(f"Overpass attempt {attempt + 1} failed: {e}. Retrying in {wait}s")
            time.sleep(wait)

    return {"grid_distance_km": None, "nearest_substation": None, "substation_voltage_kv": None}


def _fetch_all_substations():
    from ..config import get_bbox
    lat_min, lat_max, lon_min, lon_max = get_bbox()

    api = overpy.Overpass()
    query = f"""
    [out:json][timeout:120];
    (
      node["power"="substation"]({lat_min},{lon_min},{lat_max},{lon_max});
      way["power"="substation"]({lat_min},{lon_min},{lat_max},{lon_max});
    );
    out center tags;
    """
    log.info(f"Fetching all substations in bbox [{lat_min:.1f},{lat_max:.1f},{lon_min:.1f},{lon_max:.1f}]")

    for attempt in range(MAX_RETRIES):
        try:
            result = api.query(query)
            substations = []
            for node in result.nodes:
                voltage_kv = _parse_max_voltage_kv(node.tags.get("voltage"))
                substations.append({
                    "lat": float(node.lat),
                    "lon": float(node.lon),
                    "name": node.tags.get("name", "unnamed"),
                    "voltage_kv": voltage_kv,
                })
            for way in result.ways:
                voltage_kv = _parse_max_voltage_kv(way.tags.get("voltage"))
                substations.append({
                    "lat": float(way.center_lat),
                    "lon": float(way.center_lon),
                    "name": way.tags.get("name", "unnamed"),
                    "voltage_kv": voltage_kv,
                })
            log.info(f"Found {len(substations)} substations ({sum(1 for s in substations if s['voltage_kv'] >= MIN_VOLTAGE_KV)} HV)")
            return substations
        except Exception as e:
            wait = OVERPASS_DELAY * (attempt + 1) * 2
            log.warning(f"Overpass batch attempt {attempt + 1} failed: {e}. Retrying in {wait}s")
            time.sleep(wait)

    log.error("Failed to fetch substations after all retries")
    return []


def enrich_dams_with_grid(dams, max_workers=3):
    total = len(dams)
    log.info(f"Looking up nearest substation for {total} dams")

    substations = _fetch_all_substations()
    if not substations:
        log.warning("No substations found, falling back to per-dam queries")
        return _enrich_dams_one_by_one(dams, max_workers)

    hv_subs = [s for s in substations if s["voltage_kv"] >= MIN_VOLTAGE_KV]
    search_list = hv_subs if hv_subs else substations

    enriched = []
    for dam in dams:
        dam_copy = dict(dam)
        lat, lon = dam.get("lat"), dam.get("lon")
        if lat is None or lon is None:
            dam_copy["grid_distance_km"] = None
            dam_copy["nearest_substation"] = None
            dam_copy["substation_voltage_kv"] = None
            enriched.append(dam_copy)
            continue

        best_dist = float("inf")
        best_sub = None
        for sub in search_list:
            d = haversine_km(lat, lon, sub["lat"], sub["lon"])
            if d < best_dist:
                best_dist = d
                best_sub = sub

        if best_sub and best_dist < 200:
            dam_copy["grid_distance_km"] = round(best_dist, 1)
            dam_copy["nearest_substation"] = best_sub["name"]
            dam_copy["substation_voltage_kv"] = best_sub["voltage_kv"] if best_sub["voltage_kv"] > 0 else None
        else:
            dam_copy["grid_distance_km"] = None
            dam_copy["nearest_substation"] = None
            dam_copy["substation_voltage_kv"] = None
        enriched.append(dam_copy)

    with_grid = sum(1 for d in enriched if d.get("grid_distance_km") is not None)
    log.info(f"Grid enrichment complete: {with_grid}/{total} dams with grid distance")
    return enriched


def _fetch_all_water_features():
    from ..config import get_bbox
    lat_min, lat_max, lon_min, lon_max = get_bbox()

    api = overpy.Overpass()
    query = f"""
    [out:json][timeout:120];
    (
      way["waterway"="dam"]({lat_min},{lon_min},{lat_max},{lon_max});
      way["natural"="water"]({lat_min},{lon_min},{lat_max},{lon_max});
      way["landuse"="reservoir"]({lat_min},{lon_min},{lat_max},{lon_max});
      relation["natural"="water"]({lat_min},{lon_min},{lat_max},{lon_max});
      relation["landuse"="reservoir"]({lat_min},{lon_min},{lat_max},{lon_max});
      node["waterway"="dam"]({lat_min},{lon_min},{lat_max},{lon_max});
    );
    out center tags;
    """
    log.info(f"Fetching all water features in bbox [{lat_min:.1f},{lat_max:.1f},{lon_min:.1f},{lon_max:.1f}]")

    for attempt in range(MAX_RETRIES):
        try:
            result = api.query(query)
            features = []
            for node in result.nodes:
                name = node.tags.get("name") or node.tags.get("name:fr") or node.tags.get("name:ar")
                if name:
                    features.append({"lat": float(node.lat), "lon": float(node.lon), "name": name})
            for way in result.ways:
                name = way.tags.get("name") or way.tags.get("name:fr") or way.tags.get("name:ar")
                if name:
                    features.append({"lat": float(way.center_lat), "lon": float(way.center_lon), "name": name})
            for rel in result.relations:
                name = rel.tags.get("name") or rel.tags.get("name:fr") or rel.tags.get("name:ar")
                if name and hasattr(rel, "center_lat"):
                    features.append({"lat": float(rel.center_lat), "lon": float(rel.center_lon), "name": name})
            log.info(f"Found {len(features)} named water features")
            return features
        except Exception as e:
            wait = OVERPASS_DELAY * (attempt + 1) * 2
            log.warning(f"Overpass water features attempt {attempt + 1} failed: {e}. Retrying in {wait}s")
            time.sleep(wait)

    log.error("Failed to fetch water features after all retries")
    return []


def enrich_dams_with_names(dams):
    total = len(dams)
    log.info(f"Looking up OSM names for {total} dams")

    features = _fetch_all_water_features()
    if not features:
        log.warning("No water features found in OSM")
        return dams

    named = 0
    enriched = []
    for dam in dams:
        dam_copy = dict(dam)
        lat, lon = dam.get("lat"), dam.get("lon")
        if lat is None or lon is None:
            enriched.append(dam_copy)
            continue

        best_dist = float("inf")
        best_name = None
        for feat in features:
            d = haversine_km(lat, lon, feat["lat"], feat["lon"])
            if d < best_dist:
                best_dist = d
                best_name = feat["name"]

        if best_name and best_dist < 5:
            old_name = dam_copy.get("name")
            dam_copy["name"] = best_name
            alt = dam_copy.get("alt_names", [])
            if old_name and old_name not in ("Unknown", "") and old_name != best_name and old_name not in alt:
                alt.append(old_name)
            dam_copy["alt_names"] = alt
            dam_copy["name_source"] = "osm"
            dam_copy["name_distance_km"] = round(best_dist, 2)
            named += 1
        else:
            alt = dam_copy.get("alt_names", [])
            if alt:
                dam_copy["name"] = alt[0]
                dam_copy["name_source"] = "database"
            else:
                dam_copy["name_source"] = "none"

        enriched.append(dam_copy)

    log.info(f"Named {named}/{total} dams from OSM")
    return enriched


def _enrich_dams_one_by_one(dams, max_workers=3):
    total = len(dams)
    results = {}

    def lookup(i, dam):
        time.sleep(OVERPASS_DELAY * (i % max_workers))
        lat, lon = dam.get("lat"), dam.get("lon")
        if lat is None or lon is None:
            return dam["name"], {"grid_distance_km": None, "nearest_substation": None, "substation_voltage_kv": None}
        result = nearest_substation(lat, lon)
        return dam["name"], result

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(lookup, i, dam): dam for i, dam in enumerate(dams)}
        done = 0
        for future in as_completed(futures):
            name, result = future.result()
            results[name] = result
            done += 1
            if done % 10 == 0 or done == total:
                log.info(f"Grid lookup progress: {done}/{total}")

    enriched = []
    for dam in dams:
        dam_copy = dict(dam)
        grid_data = results.get(dam["name"], {})
        dam_copy["grid_distance_km"] = grid_data.get("grid_distance_km")
        dam_copy["nearest_substation"] = grid_data.get("nearest_substation")
        dam_copy["substation_voltage_kv"] = grid_data.get("substation_voltage_kv")
        enriched.append(dam_copy)

    with_grid = sum(1 for d in enriched if d.get("grid_distance_km") is not None)
    log.info(f"Grid enrichment complete: {with_grid}/{total} dams with grid distance")
    return enriched
