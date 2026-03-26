import logging

import numpy as np
import pandas as pd
import requests

from ..config import load_config
from ..geo import haversine_km, interpolate_points
from ..ingestion.elevate import get_elevation, get_elevation_batch

log = logging.getLogger(__name__)

SAMPLE_INTERVAL_M = 30


def extract_terrain_profile(upper_lat, upper_lon, lower_lat, lower_lon, upper_elev, lower_elev):
    distance_km = haversine_km(upper_lat, upper_lon, lower_lat, lower_lon)
    distance_m = distance_km * 1000
    num_points = max(int(distance_m / SAMPLE_INTERVAL_M), 10)

    lats, lons = interpolate_points(upper_lat, upper_lon, lower_lat, lower_lon, num_points)
    elevations = get_elevation_batch(lats, lons)

    distances = np.linspace(0, distance_km, num_points)

    profile = {
        "distances_km": distances.tolist(),
        "elevations_m": elevations,
        "lats": lats.tolist(),
        "lons": lons.tolist(),
        "num_points": num_points,
        "total_distance_km": distance_km,
    }

    analysis = _analyze_profile(profile, upper_elev, lower_elev)
    profile.update(analysis)

    return profile


def _analyze_profile(profile, upper_elev, lower_elev):
    elevations = profile["elevations_m"]
    valid_elevs = [e for e in elevations if e is not None]

    if not valid_elevs:
        return {
            "max_ridge_elevation_m": None,
            "max_ridge_height_above_upper_m": None,
            "tunnel_length_km": None,
            "terrain_difficulty": "unknown",
            "ridges": [],
            "obstacles": [],
        }

    max_elev = max(valid_elevs)
    min_ref = min(upper_elev or max_elev, lower_elev or max_elev)
    max_ref = max(upper_elev or 0, lower_elev or 0)

    ridge_above_upper = max_elev - max_ref if max_elev > max_ref else 0

    ridges = _detect_ridges(profile, max_ref)
    tunnel_length = _estimate_tunnel_length(profile, upper_elev, lower_elev)
    obstacles = _detect_obstacles(profile)

    config = load_config()
    max_tunnel = config["screening"].get("max_tunnel_length_km", 10)

    if tunnel_length is not None and tunnel_length > max_tunnel:
        difficulty = "infeasible"
    elif ridge_above_upper > 500:
        difficulty = "infeasible"
    elif ridge_above_upper > 200 or (tunnel_length and tunnel_length > 5):
        difficulty = "challenging"
    elif ridge_above_upper > 50 or (tunnel_length and tunnel_length > 2):
        difficulty = "moderate"
    else:
        difficulty = "easy"

    return {
        "max_ridge_elevation_m": max_elev,
        "max_ridge_height_above_upper_m": ridge_above_upper,
        "tunnel_length_km": round(tunnel_length, 2) if tunnel_length else 0,
        "terrain_difficulty": difficulty,
        "ridges": ridges,
        "obstacles": obstacles,
    }


def _detect_ridges(profile, reference_elev):
    elevations = profile["elevations_m"]
    distances = profile["distances_km"]
    ridges = []

    in_ridge = False
    ridge_start = None
    ridge_max = None
    ridge_max_dist = None

    for i, elev in enumerate(elevations):
        if elev is None:
            continue
        if elev > reference_elev + 20:
            if not in_ridge:
                in_ridge = True
                ridge_start = distances[i]
                ridge_max = elev
                ridge_max_dist = distances[i]
            elif elev > ridge_max:
                ridge_max = elev
                ridge_max_dist = distances[i]
        elif in_ridge:
            ridges.append({
                "start_km": round(ridge_start, 2),
                "end_km": round(distances[i], 2),
                "peak_km": round(ridge_max_dist, 2),
                "peak_elevation_m": ridge_max,
                "height_above_ref_m": ridge_max - reference_elev,
            })
            in_ridge = False

    if in_ridge:
        ridges.append({
            "start_km": round(ridge_start, 2),
            "end_km": round(distances[-1], 2),
            "peak_km": round(ridge_max_dist, 2),
            "peak_elevation_m": ridge_max,
            "height_above_ref_m": ridge_max - reference_elev,
        })

    return ridges


def _estimate_tunnel_length(profile, upper_elev, lower_elev):
    if upper_elev is None or lower_elev is None:
        return 0

    elevations = profile["elevations_m"]
    distances = profile["distances_km"]
    n = len(distances)

    direct_line = np.linspace(upper_elev, lower_elev, n)

    tunnel_segments = 0
    for i, elev in enumerate(elevations):
        if elev is None:
            continue
        if elev > direct_line[i] + 10:
            if i < n - 1:
                tunnel_segments += distances[i + 1] - distances[i]

    return tunnel_segments


def _detect_obstacles(profile):
    obstacles = []
    lats = profile["lats"]
    lons = profile["lons"]

    sample_points = min(5, len(lats))
    indices = np.linspace(0, len(lats) - 1, sample_points, dtype=int)

    for idx in indices:
        lat, lon = lats[idx], lons[idx]
        point_obstacles = _check_osm_obstacles(lat, lon)
        for obs in point_obstacles:
            obs["distance_km"] = round(profile["distances_km"][idx], 2)
            obstacles.append(obs)

    return obstacles


def _check_osm_obstacles(lat, lon):
    obstacles = []
    radius = 500

    query = f"""
    [out:json][timeout:10];
    (
      way["waterway"="river"](around:{radius},{lat},{lon});
      way["landuse"="residential"](around:{radius},{lat},{lon});
      way["highway"="motorway"](around:{radius},{lat},{lon});
      way["highway"="trunk"](around:{radius},{lat},{lon});
      way["railway"="rail"](around:{radius},{lat},{lon});
    );
    out tags;
    """
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=10,
        )
        if resp.status_code != 200:
            return obstacles

        data = resp.json()
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            if "waterway" in tags:
                obstacles.append({"type": "river_crossing", "name": tags.get("name", "unnamed")})
            elif "landuse" in tags and tags["landuse"] == "residential":
                obstacles.append({"type": "urban_area", "name": tags.get("name", "settlement")})
            elif "highway" in tags:
                obstacles.append({"type": "road_crossing", "name": tags.get("name", tags["highway"])})
            elif "railway" in tags:
                obstacles.append({"type": "railway_crossing", "name": tags.get("name", "rail")})
    except Exception:
        pass

    return obstacles


def analyze_all_pairs(viable_pairs_df):
    log.info(f"Analyzing terrain for {len(viable_pairs_df)} pairs")
    results = []

    for i, (_, pair) in enumerate(viable_pairs_df.iterrows()):
        if i % 10 == 0:
            log.info(f"Terrain analysis progress: {i}/{len(viable_pairs_df)}")

        profile = extract_terrain_profile(
            pair["upper_lat"], pair["upper_lon"],
            pair["lower_lat"], pair["lower_lon"],
            pair["upper_elevation_m"], pair["lower_elevation_m"],
        )

        row = pair.to_dict()
        row["terrain_difficulty"] = profile["terrain_difficulty"]
        row["tunnel_length_km"] = profile["tunnel_length_km"]
        row["max_ridge_elevation_m"] = profile["max_ridge_elevation_m"]
        row["ridge_above_upper_m"] = profile["max_ridge_height_above_upper_m"]
        row["num_ridges"] = len(profile["ridges"])
        row["num_obstacles"] = len(profile["obstacles"])

        obstacle_types = [o["type"] for o in profile["obstacles"]]
        row["river_crossings"] = obstacle_types.count("river_crossing")
        row["urban_areas"] = obstacle_types.count("urban_area")

        row["terrain_profile"] = profile
        results.append(row)

    result_df = pd.DataFrame(results)

    infeasible = result_df[result_df["terrain_difficulty"] == "infeasible"]
    log.info(
        f"Terrain analysis complete: {len(result_df) - len(infeasible)} feasible, "
        f"{len(infeasible)} infeasible"
    )
    return result_df
