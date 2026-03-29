import logging
import math
import re

import pandas as pd

from ..geo import haversine_m

log = logging.getLogger(__name__)

PROXIMITY_THRESHOLD_M = 2000


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


def _normalize(name):
    if not name or not isinstance(name, str):
        return ""
    name = name.strip().lower()
    name = re.sub(r"[''`]", "'", name)
    name = re.sub(r"\s+", " ", name)
    for prefix in ["barrage d'", "barrage de ", "barrage du ", "barrage el ",
                    "barrage al ", "barrage ", "dam ", "sdd ", "reservoir "]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    name = re.sub(r"[^a-z0-9 ]", "", name)
    return name.strip()


def _names_match(name1, name2):
    if not name1 or not name2:
        return False
    n1 = _normalize(name1)
    n2 = _normalize(name2)
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
    if n1.replace(" ", "") == n2.replace(" ", ""):
        return True
    words1 = n1.split()
    words2 = n2.split()
    if len(words1) == len(words2) and len(words1) >= 3:
        mismatches = sum(1 for a, b in zip(sorted(words1), sorted(words2)) if a != b)
        if mismatches <= 1:
            return True
    return False


def merge_from_staged(staged_sources, config):
    country_code = config.get("country_code", "DAM")
    backbone = config.get("backbone_source")
    priority = config.get("sources_priority", list(staged_sources.keys()))
    threshold = config.get("proximity_threshold_m", 2000)
    aliases = config.get("name_aliases", {})
    known_coords = config.get("known_coordinates", {})

    dams = []
    used_names = set()

    if backbone and backbone in staged_sources:
        for record in staged_sources[backbone]:
            dam = _record_to_dam(record, backbone)
            dams.append(dam)
            if dam.get("name"):
                used_names.add(_normalize(dam["name"]))

    for source_name in priority:
        if source_name == backbone or source_name not in staged_sources:
            continue
        for record in staged_sources[source_name]:
            name = record.get("name", "")
            norm = _normalize(name)

            alias_target = aliases.get(name)
            matched = False

            for dam in dams:
                dam_norm = _normalize(dam.get("name", ""))
                alias_norm = _normalize(alias_target) if alias_target else None

                if (dam_norm and norm and (dam_norm == norm or (alias_norm and alias_norm == dam_norm))) or \
                   (dam_norm and norm and _names_match(name, dam["name"])):
                    _enrich_dam(dam, record, source_name)
                    matched = True
                    break

            if not matched and record.get("lat") is not None and record.get("lon") is not None:
                for dam in dams:
                    if _coord_missing(dam):
                        continue
                    try:
                        dist = haversine_m(record["lat"], record["lon"], dam["lat"], dam["lon"])
                        if dist < threshold:
                            _enrich_dam(dam, record, source_name)
                            matched = True
                            break
                    except (TypeError, ValueError):
                        continue

            if not matched:
                dam = _record_to_dam(record, source_name)
                dams.append(dam)

    for dam in dams:
        coords = known_coords.get(dam.get("name"))
        if coords and _coord_missing(dam):
            dam["lat"] = coords[0]
            dam["lon"] = coords[1]

    dams.sort(key=lambda d: d.get("name", ""))
    for i, dam in enumerate(dams):
        dam["id"] = f"{country_code}-{i + 1:03d}"

    log.info(f"Staged merge: {len(dams)} dams from {len(staged_sources)} sources")
    return pd.DataFrame(dams)


def _record_to_dam(record, source_name):
    return {
        "name": record.get("name"),
        "alt_names": [record["alt_name"]] if record.get("alt_name") else [],
        "lat": record.get("lat"),
        "lon": record.get("lon"),
        "height_m": record.get("height_m"),
        "capacity_mcm": record.get("capacity_mcm"),
        "surface_area_km2": record.get("surface_area_km2"),
        "year_built": record.get("year_built"),
        "river": record.get("river"),
        "basin": record.get("basin"),
        "purpose": record.get("purpose", []),
        "nearest_city": record.get("nearest_city"),
        "elevation_db_m": record.get("elevation_m") or record.get("elevation_db_m"),
        "sources": [source_name],
        "grand_id": record.get("grand_id"),
        "status": "operational",
    }


def _enrich_dam(dam, record, source_name):
    if source_name not in dam.get("sources", []):
        dam.setdefault("sources", []).append(source_name)

    if _coord_missing(dam) and record.get("lat") is not None:
        dam["lat"] = record["lat"]
        dam["lon"] = record["lon"]

    for field in ["height_m", "capacity_mcm", "surface_area_km2", "year_built",
                  "river", "basin", "nearest_city", "elevation_db_m", "grand_id"]:
        if dam.get(field) is None and record.get(field) is not None:
            dam[field] = record[field]

    rec_name = record.get("name", "")
    if rec_name and rec_name != dam.get("name") and rec_name not in dam.get("alt_names", []):
        dam.setdefault("alt_names", []).append(rec_name)
