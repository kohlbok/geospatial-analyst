import logging
from itertools import combinations

import numpy as np
import pandas as pd

from ..geo import haversine_km

log = logging.getLogger(__name__)


def _valid(val):
    if val is None:
        return False
    try:
        return not np.isnan(float(val))
    except (ValueError, TypeError):
        return False


def generate_pairs(dam_registry):
    dams = dam_registry.to_dict("records")
    excluded_statuses = {"removed", "operational psh", "existing_psh"}
    valid_dams = [d for d in dams if _valid(d.get("lat")) and _valid(d.get("lon")) and _valid(d.get("elevation_wall_m")) and d.get("status", "").strip().lower() not in excluded_statuses]
    n = len(valid_dams)
    total_pairs = n * (n - 1) // 2
    log.info(f"Generating pairs from {n} dams with coords+elevation ({total_pairs} combinations, {len(dams) - n} excluded)")

    pairs = []
    for i, j in combinations(range(n), 2):
        dam_a = valid_dams[i]
        dam_b = valid_dams[j]

        elev_a = dam_a["elevation_wall_m"]
        elev_b = dam_b["elevation_wall_m"]

        distance_km = haversine_km(dam_a["lat"], dam_a["lon"], dam_b["lat"], dam_b["lon"])

        if elev_a >= elev_b:
            upper, lower = dam_a, dam_b
            head = elev_a - elev_b
        else:
            upper, lower = dam_b, dam_a
            head = elev_b - elev_a

        if head == 0:
            continue

        distance_head_ratio = (distance_km * 1000) / head

        upper_grid = upper.get("grid_distance_km")
        lower_grid = lower.get("grid_distance_km")
        pair_grid = None
        if _valid(upper_grid) and _valid(lower_grid):
            pair_grid = round(min(float(upper_grid), float(lower_grid)), 1)
        elif _valid(upper_grid):
            pair_grid = round(float(upper_grid), 1)
        elif _valid(lower_grid):
            pair_grid = round(float(lower_grid), 1)

        pairs.append({
            "upper_dam_id": upper["id"],
            "upper_dam_name": upper["name"],
            "upper_lat": upper["lat"],
            "upper_lon": upper["lon"],
            "upper_elevation_m": upper.get("elevation_wall_m"),
            "upper_capacity_mcm": upper.get("capacity_mcm"),
            "lower_dam_id": lower["id"],
            "lower_dam_name": lower["name"],
            "lower_lat": lower["lat"],
            "lower_lon": lower["lon"],
            "lower_elevation_m": lower.get("elevation_wall_m"),
            "lower_capacity_mcm": lower.get("capacity_mcm"),
            "upper_status": upper.get("status"),
            "lower_status": lower.get("status"),
            "upper_fill_rate_pct": upper.get("fill_rate_pct"),
            "lower_fill_rate_pct": lower.get("fill_rate_pct"),
            "head_m": head,
            "distance_km": round(distance_km, 2),
            "distance_head_ratio": round(distance_head_ratio, 2),
            "grid_distance_km": pair_grid,
        })

    result = pd.DataFrame(pairs)
    log.info(f"Generated {len(result)} valid pairs (with elevation data)")
    return result
