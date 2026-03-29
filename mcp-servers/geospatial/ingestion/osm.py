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


def enrich_dams_with_grid(dams, max_workers=3):
    total = len(dams)
    log.info(f"Looking up nearest substation for {total} dams (max {max_workers} parallel)")

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
