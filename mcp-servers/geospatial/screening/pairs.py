import logging
from itertools import combinations

import numpy as np
import pandas as pd

from ..geo import haversine_km

log = logging.getLogger(__name__)


def generate_pairs(dam_registry):
    dams = dam_registry.to_dict("records")
    n = len(dams)
    total_pairs = n * (n - 1) // 2
    log.info(f"Generating pairs from {n} dams ({total_pairs} combinations)")

    pairs = []
    for i, j in combinations(range(n), 2):
        dam_a = dams[i]
        dam_b = dams[j]

        if dam_a.get("lat") is None or dam_b.get("lat") is None:
            continue

        elev_a = dam_a.get("elevation_wall_m")
        elev_b = dam_b.get("elevation_wall_m")
        if elev_a is None or elev_b is None:
            continue

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
            "head_m": head,
            "distance_km": round(distance_km, 2),
            "distance_head_ratio": round(distance_head_ratio, 2),
        })

    result = pd.DataFrame(pairs)
    log.info(f"Generated {len(result)} valid pairs (with elevation data)")
    return result
