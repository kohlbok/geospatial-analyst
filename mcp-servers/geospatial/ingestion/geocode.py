import logging
import time

import requests

from ..config import load_config, get_bbox

log = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "PSH-Screener/1.0"}


def _haversine_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _nominatim_coords(place, country=None):
    q = f"{place}, {country}" if country else place
    try:
        time.sleep(0.3)
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": q, "format": "json", "limit": 1},
            headers=NOMINATIM_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        log.debug(f"Nominatim failed for '{place}': {e}")
    return None, None


def _overpass_dams_near(lat, lon, radius_km=40):
    radius_m = radius_km * 1000
    query = f"""
    [out:json][timeout:30];
    (
      node["waterway"="dam"](around:{radius_m},{lat},{lon});
      way["waterway"="dam"](around:{radius_m},{lat},{lon});
      node["man_made"="dam"](around:{radius_m},{lat},{lon});
      way["man_made"="dam"](around:{radius_m},{lat},{lon});
    );
    out center tags;
    """
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=35)
        resp.raise_for_status()
        dams = []
        for el in resp.json().get("elements", []):
            lat_el = el.get("lat") or el.get("center", {}).get("lat")
            lon_el = el.get("lon") or el.get("center", {}).get("lon")
            if lat_el and lon_el:
                tags = el.get("tags", {})
                dams.append({
                    "lat": float(lat_el),
                    "lon": float(lon_el),
                    "name": tags.get("name", tags.get("name:fr", tags.get("name:en", ""))),
                })
        return dams
    except Exception as e:
        log.debug(f"Overpass near ({lat},{lon}) failed: {e}")
        return []


def _overpass_name_search(name, bbox):
    lat_min, lat_max, lon_min, lon_max = bbox
    bbox_str = f"{lat_min},{lon_min},{lat_max},{lon_max}"
    for search_name in [name, f"dam {name}", f"barrage {name}"]:
        query = f"""
        [out:json][timeout:20];
        (
          node["name"~"{search_name}",i]["waterway"="dam"]({bbox_str});
          way["name"~"{search_name}",i]["waterway"="dam"]({bbox_str});
          node["name"~"{search_name}",i]["man_made"="dam"]({bbox_str});
          way["name"~"{search_name}",i]["man_made"="dam"]({bbox_str});
        );
        out center;
        """
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=25)
            for el in resp.json().get("elements", []):
                lat = el.get("lat") or el.get("center", {}).get("lat")
                lon = el.get("lon") or el.get("center", {}).get("lon")
                if lat and lon:
                    return float(lat), float(lon), "osm_name"
        except Exception:
            pass
    return None, None, None


def geocode_dam(name, river=None, nearest_city=None):
    config = load_config()
    country = config.get("country")
    bbox = get_bbox()

    name = str(name).strip() if name else ""
    river = str(river).strip() if river and str(river).lower() not in ("nan", "none", "") else None
    city = str(nearest_city).strip() if nearest_city and str(nearest_city).lower() not in ("nan", "none", "") else None

    if name:
        lat, lon, src = _overpass_name_search(name, bbox)
        if lat:
            return lat, lon, src

    if city:
        city_lat, city_lon = _nominatim_coords(city, country)
        if city_lat:
            nearby = _overpass_dams_near(city_lat, city_lon, radius_km=40)
            if len(nearby) == 1:
                d = nearby[0]
                return d["lat"], d["lon"], f"osm_near_city:{city}"
            if river and nearby:
                for d in nearby:
                    if river.lower() in d["name"].lower() or d["name"].lower() in river.lower():
                        return d["lat"], d["lon"], f"osm_city_river:{city}"
            if nearby:
                closest = min(nearby, key=lambda d: _haversine_km(city_lat, city_lon, d["lat"], d["lon"]))
                dist = _haversine_km(city_lat, city_lon, closest["lat"], closest["lon"])
                if dist < 20:
                    return closest["lat"], closest["lon"], f"osm_nearest:{city}:{dist:.1f}km"

    for query in filter(None, [
        f"{name} dam {country}" if name else None,
        f"{name} dam" if name else None,
    ]):
        time.sleep(0.3)
        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1},
                headers=NOMINATIM_HEADERS,
                timeout=10,
            )
            results = resp.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"]), "nominatim"
        except Exception:
            pass

    return None, None, None


def geocode_unlocated(dams):
    import pandas as pd
    unlocated = [d for d in dams if d.get("lat") is None or (isinstance(d.get("lat"), float) and pd.isna(d["lat"]))]
    if not unlocated:
        return dams, 0

    log.info(f"Attempting to geocode {len(unlocated)} unlocated dams")
    found = 0

    for dam in unlocated:
        lat, lon, src = geocode_dam(
            name=dam.get("name"),
            river=dam.get("river"),
            nearest_city=dam.get("nearest_city"),
        )
        if lat:
            dam["lat"] = lat
            dam["lon"] = lon
            dam["geocode_source"] = src
            found += 1
            log.info(f"  {dam.get('name')} -> ({lat:.4f}, {lon:.4f}) [{src}]")

    log.info(f"Geocoded {found}/{len(unlocated)} unlocated dams")
    return dams, found
