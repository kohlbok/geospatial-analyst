import logging
import math

import numpy as np

from .basins import find_candidate_basins
from .cost import optimize_candidate

log = logging.getLogger(__name__)


def _dam_elevation(dam):
    for key in ("elevation_m", "elevation_wall_m", "elev_cop90_m"):
        val = dam.get(key)
        if val is None:
            continue
        try:
            v = float(val)
            if not math.isnan(v):
                return v
        except (ValueError, TypeError):
            continue
    return None


def tier1_screen(dam, patch, params):
    p2 = params.get("siting", {})
    min_head = p2.get("min_head_m", 100)
    max_ratio = p2.get("max_distance_head_ratio", 15.0)
    search_radius_km = p2.get("search_radius_km", 20)

    dam_lat = dam.get("lat")
    dam_lon = dam.get("lon")
    dam_elev = _dam_elevation(dam)
    if dam_lat is None or dam_lon is None or dam_elev is None:
        return {"viable_up": False, "viable_down": False, "kill_reason": "missing_coordinates_or_elevation"}

    data = patch["data"]
    rows, cols = data.shape

    row_idx = np.arange(rows)[:, None]
    col_idx = np.arange(cols)[None, :]
    cell_lats = patch["lat_max"] - row_idx * patch["lat_res"]
    cell_lons = patch["lon_min"] + col_idx * patch["lon_res"]

    dlat = np.radians(cell_lats - dam_lat)
    dlon = np.radians(cell_lons - dam_lon)
    a = np.sin(dlat / 2) ** 2 + math.cos(math.radians(dam_lat)) * np.cos(np.radians(cell_lats)) * np.sin(dlon / 2) ** 2
    dist_km = 6371.0 * 2 * np.arcsin(np.sqrt(a))

    dist_m = dist_km * 1000.0
    required_head = np.maximum(min_head, dist_m / max_ratio)
    head = data - dam_elev

    valid = (~np.isnan(data)) & (dist_km > 0) & (dist_km <= search_radius_km)
    viable_up_mask = valid & (head >= required_head)
    viable_down_mask = valid & (head <= -required_head)

    viable_up = bool(viable_up_mask.any())
    viable_down = bool(viable_down_mask.any())

    if not viable_up and not viable_down:
        max_elev = float(np.nanmax(data))
        min_elev = float(np.nanmin(data))
        flat = (max_elev - min_elev) < min_head
        if flat:
            return {"viable_up": False, "viable_down": False, "kill_reason": "flat_terrain",
                    "max_head_up_m": round(max_elev - min_elev, 1), "best_up_dist_km": None,
                    "max_head_down_m": 0.0, "best_down_dist_km": None}
        best_ratio_head = float(np.nanmax(np.abs(head[valid]))) if valid.any() else 0.0
        best_ratio_dist = float(dist_km[valid][np.nanargmax(np.abs(head[valid]))]) if valid.any() else 0.0
        return {"viable_up": False, "viable_down": False, "kill_reason": "ratio_too_high",
                "max_head_up_m": round(best_ratio_head, 1), "best_up_dist_km": round(best_ratio_dist, 2),
                "max_head_down_m": 0.0, "best_down_dist_km": None}

    result = {"viable_up": viable_up, "viable_down": viable_down, "kill_reason": None}

    if viable_up:
        masked_head = np.where(viable_up_mask, head, -np.inf)
        idx = np.unravel_index(np.argmax(masked_head), masked_head.shape)
        result["max_head_up_m"] = round(float(head[idx]), 1)
        result["best_up_dist_km"] = round(float(dist_km[idx]), 2)
    else:
        result["max_head_up_m"] = 0.0
        result["best_up_dist_km"] = None

    if viable_down:
        masked_head = np.where(viable_down_mask, -head, -np.inf)
        idx = np.unravel_index(np.argmax(masked_head), masked_head.shape)
        result["max_head_down_m"] = round(float(-head[idx]), 1)
        result["best_down_dist_km"] = round(float(dist_km[idx]), 2)
    else:
        result["max_head_down_m"] = 0.0
        result["best_down_dist_km"] = None

    return result


def _closest_attempt(near_misses):
    if not near_misses:
        return None
    return max(near_misses, key=lambda m: m["stage_rank"])["detail"]


def scan_and_analyze(dam, patch, tier1_result, params):
    dam_lat = dam.get("lat")
    dam_lon = dam.get("lon")
    dam_elev = _dam_elevation(dam)
    if dam_lat is None or dam_lon is None or dam_elev is None:
        return [], {"missing_data": 1}, None

    basins, basin_near_misses = find_candidate_basins(patch, dam_lat, dam_lon, dam_elev, params)
    if not basins:
        return [], {"no_basins": 1}, _closest_attempt(basin_near_misses)

    max_t3 = params.get("siting", {}).get("max_basins_per_dam_tier3", 3)
    existing_capacity_mcm = dam.get("capacity_mcm")

    optimized_viable = []
    kill_reasons = {"no_feasible_optimum": 0}
    all_near_misses = list(basin_near_misses)

    for basin in basins:
        direction = basin["direction"]
        if direction == "up" and not tier1_result.get("viable_up"):
            continue
        if direction == "down" and not tier1_result.get("viable_down"):
            continue

        result, cost_kill = optimize_candidate(basin, dam_elev, existing_capacity_mcm, params)
        if result is None:
            kill_reasons["no_feasible_optimum"] += 1
            if cost_kill:
                all_near_misses.append(cost_kill)
            continue

        candidate = dict(basin)
        candidate.update(result)
        candidate["dam_id"] = dam.get("id")
        candidate["dam_name"] = dam.get("name")
        candidate["dam_lat"] = dam_lat
        candidate["dam_lon"] = dam_lon
        candidate["dam_elevation_m"] = dam_elev
        candidate["grid_distance_km"] = dam.get("grid_distance_km")
        candidate.pop("area_fill_curve", None)
        optimized_viable.append(candidate)

    optimized_viable.sort(key=lambda c: c.get("capex_per_mwh_usd") or float("inf"))
    per_direction = {"up": [], "down": []}
    for c in optimized_viable:
        d = c.get("direction", "up")
        if len(per_direction[d]) < max_t3:
            per_direction[d].append(c)
    final = per_direction["up"] + per_direction["down"]
    final.sort(key=lambda c: c.get("capex_per_mwh_usd") or float("inf"))
    if kill_reasons["no_feasible_optimum"] == 0:
        kill_reasons.pop("no_feasible_optimum")
    closest = None if final else _closest_attempt(all_near_misses)
    return final, kill_reasons, closest
