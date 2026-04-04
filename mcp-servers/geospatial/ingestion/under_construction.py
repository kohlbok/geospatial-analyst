import logging
import re
import time

import requests

from ..config import load_config, get_bbox

log = logging.getLogger(__name__)

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
WIKIDATA_HEADERS = {"User-Agent": "PSH-Screener/1.0", "Accept": "application/json"}

WD_UNDER_CONSTRUCTION = "wd:Q55606045"
WD_PLANNED = "wd:Q1758"
WD_DAM = "wd:Q12323"


def _safe_float(val):
    try:
        v = float(str(val).replace(",", ".").strip())
        return v if -1e9 < v < 1e9 else None
    except (ValueError, TypeError):
        return None


def fetch_from_wikidata():
    lat_min, lat_max, lon_min, lon_max = get_bbox()
    sparql = f"""
SELECT ?item ?itemLabel ?coord ?heightVal ?capacityVal ?riverLabel WHERE {{
  ?item wdt:P31/wdt:P279* {WD_DAM} .
  ?item wdt:P625 ?coord .
  ?item wdt:P5817 ?status .
  VALUES ?status {{ {WD_UNDER_CONSTRUCTION} {WD_PLANNED} }}
  FILTER(geof:latitude(?coord) >= {lat_min} && geof:latitude(?coord) <= {lat_max} &&
         geof:longitude(?coord) >= {lon_min} && geof:longitude(?coord) <= {lon_max})
  OPTIONAL {{ ?item wdt:P2048 ?heightVal }}
  OPTIONAL {{ ?item wdt:P2695 ?capacityVal }}
  OPTIONAL {{ ?item wdt:P469 ?river . ?river rdfs:label ?riverLabel . FILTER(LANG(?riverLabel) = "en") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,fr,ar" }}
}}
LIMIT 200
"""
    try:
        time.sleep(0.5)
        resp = requests.get(
            WIKIDATA_SPARQL_URL,
            params={"query": sparql, "format": "json"},
            headers=WIKIDATA_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
    except Exception as e:
        log.warning(f"WikiData SPARQL failed: {e}")
        return []

    records = []
    seen = set()
    for b in bindings:
        qid = b.get("item", {}).get("value", "").split("/")[-1]
        if qid in seen:
            continue
        seen.add(qid)

        coord_str = b.get("coord", {}).get("value", "")
        m = re.search(r"Point\(([+-]?\d+\.?\d*)\s+([+-]?\d+\.?\d*)\)", coord_str)
        if not m:
            continue
        lon, lat = float(m.group(1)), float(m.group(2))
        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            continue

        records.append({
            "name": b.get("itemLabel", {}).get("value", ""),
            "lat": lat,
            "lon": lon,
            "height_m": _safe_float(b.get("heightVal", {}).get("value")) if b.get("heightVal") else None,
            "capacity_mcm": _safe_float(b.get("capacityVal", {}).get("value")) if b.get("capacityVal") else None,
            "river": b.get("riverLabel", {}).get("value") if b.get("riverLabel") else None,
            "status": "Under Construction",
            "source": f"wikidata:{qid}",
        })

    log.info(f"WikiData: {len(records)} under-construction dams in bbox")
    return records


def fetch_from_osm():
    lat_min, lat_max, lon_min, lon_max = get_bbox()
    bbox_str = f"{lat_min},{lon_min},{lat_max},{lon_max}"
    query = f"""
[out:json][timeout:30];
(
  node["construction"="dam"]({bbox_str});
  way["construction"="dam"]({bbox_str});
  node["waterway"="dam"]["construction"="yes"]({bbox_str});
  way["waterway"="dam"]["construction"="yes"]({bbox_str});
);
out center tags;
"""
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=35)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except Exception as e:
        log.warning(f"OSM under-construction query failed: {e}")
        return []

    records = []
    for el in elements:
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not lat or not lon:
            continue
        tags = el.get("tags", {})
        records.append({
            "name": (tags.get("name") or tags.get("name:fr") or tags.get("name:en") or "").strip(),
            "lat": float(lat),
            "lon": float(lon),
            "height_m": _safe_float(tags.get("height")),
            "status": "Under Construction",
            "source": f"osm:{el.get('type', '')}/{el.get('id', '')}",
        })

    log.info(f"OSM: {len(records)} under-construction dams in bbox")
    return records


def fetch_all_under_construction():
    records = []
    records.extend(fetch_from_wikidata())
    records.extend(fetch_from_osm())

    if not records:
        log.info("No under-construction dams found from any source")
        return []

    with_coords = [r for r in records if r.get("lat") is not None]
    log.info(f"Under-construction total: {len(with_coords)} dams with coordinates")
    return with_coords
