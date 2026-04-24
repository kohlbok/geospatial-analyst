import logging
import math

import numpy as np
from scipy import ndimage
from skimage.measure import find_contours
from skimage.morphology import reconstruction

from ..terrain.dem import pixel_to_latlon

log = logging.getLogger(__name__)

MIN_BASIN_PIXELS = 50
EPSILON_DEPTH_M = 0.5


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _pixel_area_m2(patch, center_lat):
    lat_m = patch["lat_res"] * 111_000.0
    lon_m = patch["lon_res"] * 111_000.0 * math.cos(math.radians(center_lat))
    return lat_m * lon_m


def fill_sinks(dem):
    nan_mask = np.isnan(dem)
    if nan_mask.all():
        return dem.copy()
    finite_max = float(np.nanmax(dem))
    clean = np.where(nan_mask, finite_max, dem).astype(np.float32)
    seed = np.full_like(clean, finite_max)
    seed[0, :] = clean[0, :]
    seed[-1, :] = clean[-1, :]
    seed[:, 0] = clean[:, 0]
    seed[:, -1] = clean[:, -1]
    filled = reconstruction(seed, clean, method="erosion")
    return filled.astype(np.float32)


def label_depressions(dem, filled, epsilon_m=EPSILON_DEPTH_M):
    depth = filled - dem
    mask = depth > epsilon_m
    mask &= ~np.isnan(dem)
    labels, _ = ndimage.label(mask)
    return labels


def _basin_centroid(mask, patch):
    rows, cols = np.where(mask)
    if len(rows) == 0:
        return None, None
    r = float(rows.mean())
    c = float(cols.mean())
    lat = patch["lat_max"] - r * patch["lat_res"]
    lon = patch["lon_min"] + c * patch["lon_res"]
    return lat, lon


def _flooded_polygon(mask, dem, patch, fill_level, max_points=120):
    submerged = mask & ~np.isnan(dem) & (dem <= fill_level)
    if not submerged.any():
        return []
    padded = np.pad(submerged.astype(np.float32), 1, mode="constant", constant_values=0)
    contours = find_contours(padded, 0.5)
    if not contours:
        return []
    largest = max(contours, key=len)
    step = max(1, len(largest) // max_points)
    lat_max = patch["lat_max"]
    lon_min = patch["lon_min"]
    lat_res = patch["lat_res"]
    lon_res = patch["lon_res"]
    points = []
    for r, c in largest[::step]:
        rr = r - 1
        cc = c - 1
        points.append([float(lat_max - rr * lat_res), float(lon_min + cc * lon_res)])
    if len(points) >= 3 and points[0] != points[-1]:
        points.append(points[0])
    return points


def _basin_saddle_location(mask, patch, pixel_area_m2, saddle_elev, dem):
    dilated = ndimage.binary_dilation(mask)
    boundary_outside = dilated & ~mask
    rows, cols = np.where(boundary_outside)
    if len(rows) == 0:
        return None
    r_c = int(round(rows.mean()))
    c_c = int(round(cols.mean()))
    lat, lon = pixel_to_latlon(r_c, c_c, patch)
    outside_elevs = dem[boundary_outside]
    finite = outside_elevs[~np.isnan(outside_elevs)]
    if len(finite) == 0:
        band_pixels = int(boundary_outside.sum())
    else:
        near_saddle = np.isfinite(outside_elevs) & (np.abs(outside_elevs - saddle_elev) < 2.0)
        band_pixels = int(near_saddle.sum())
        if band_pixels == 0:
            band_pixels = int(boundary_outside.sum())
    width_m = math.sqrt(max(band_pixels, 1) * pixel_area_m2)
    return {"lat": lat, "lon": lon, "width_m": width_m}


def _basin_sink_latlon(mask, dem, patch):
    masked = np.where(mask, dem, np.inf)
    idx = np.unravel_index(np.nanargmin(masked), masked.shape)
    return pixel_to_latlon(idx[0], idx[1], patch)


def _area_fill_curve(mask, dem, sink_elev, saddle_elev, pixel_area_m2, n_samples,
                     max_wall_height_m=0.0, max_fill_depth_m=None, max_footprint_area_m2=None):
    if saddle_elev <= sink_elev:
        return [], False
    basin_dem = dem[mask]
    basin_dem = basin_dem[~np.isnan(basin_dem)]
    if len(basin_dem) == 0:
        return [], False
    levels = list(np.linspace(sink_elev, saddle_elev, max(n_samples, 2)))
    if max_wall_height_m > 0:
        top = saddle_elev + max_wall_height_m
        extras = list(np.linspace(saddle_elev, top, 5))[1:]
        levels.extend(extras)
    samples = []
    saddle_area = None
    saddle_volume = None
    for level in levels:
        if level <= saddle_elev or saddle_area is None:
            submerged = basin_dem <= level
            n = int(submerged.sum())
            if n == 0:
                samples.append({"fill_m": float(level), "area_m2": 0.0, "volume_m3": 0.0})
                continue
            depths = level - basin_dem[submerged]
            area_m2 = float(n * pixel_area_m2)
            volume_m3 = float(depths.sum()) * pixel_area_m2
            if abs(level - saddle_elev) < 1e-6:
                saddle_area = area_m2
                saddle_volume = volume_m3
        else:
            extra_height = level - saddle_elev
            area_m2 = saddle_area
            volume_m3 = saddle_volume + saddle_area * extra_height
        samples.append({
            "fill_m": float(level),
            "area_m2": area_m2,
            "volume_m3": volume_m3,
        })

    capped = False
    if max_fill_depth_m is not None:
        filtered = [s for s in samples if (s["fill_m"] - sink_elev) <= max_fill_depth_m]
        if len(filtered) < len(samples):
            capped = True
        samples = filtered
    if max_footprint_area_m2 is not None:
        filtered = [s for s in samples if s["area_m2"] <= max_footprint_area_m2]
        if len(filtered) < len(samples):
            capped = True
        samples = filtered
    return samples, capped


def find_candidate_basins(patch, dam_lat, dam_lon, dam_elev, params):
    p2 = params.get("siting", {})
    min_head_m = p2.get("min_head_m", 100)
    max_ratio = p2.get("max_distance_head_ratio", 15.0)
    max_saddle_width_m = p2.get("max_saddle_width_m", 500)
    max_wall_height_m = p2.get("max_wall_height_m", 30)
    max_fill_depth_m = p2.get("max_fill_depth_m", 30)
    max_footprint_area_m2 = p2.get("max_footprint_area_m2", 280_000)
    n_samples = p2.get("fill_depth_samples", 20)
    max_basins = p2.get("max_basins_per_dam_tier2", 10)

    dem = patch["data"]
    if np.all(np.isnan(dem)):
        return []

    filled = fill_sinks(dem)
    labels = label_depressions(dem, filled)

    pixel_area = _pixel_area_m2(patch, dam_lat)

    candidates = []
    unique_labels = np.unique(labels)
    for basin_id in unique_labels:
        if basin_id == 0:
            continue
        mask = labels == basin_id
        if mask.sum() < MIN_BASIN_PIXELS:
            continue

        basin_dem = dem[mask]
        finite = basin_dem[~np.isnan(basin_dem)]
        if len(finite) == 0:
            continue
        sink_elev = float(finite.min())
        saddle_elev = float(filled[mask][0])

        if saddle_elev - sink_elev < 5:
            continue

        saddle = _basin_saddle_location(mask, patch, pixel_area, saddle_elev, dem)
        if saddle is None:
            continue
        if saddle["width_m"] > max_saddle_width_m:
            continue

        full_curve, basin_capped = _area_fill_curve(
            mask, dem,
            sink_elev=sink_elev, saddle_elev=saddle_elev,
            pixel_area_m2=pixel_area, n_samples=n_samples,
            max_wall_height_m=max_wall_height_m,
            max_fill_depth_m=max_fill_depth_m,
            max_footprint_area_m2=max_footprint_area_m2,
        )
        if not full_curve:
            continue

        sink_lat, sink_lon = _basin_sink_latlon(mask, dem, patch)
        centroid_lat, centroid_lon = _basin_centroid(mask, patch)
        max_capped_fill = max(s["fill_m"] for s in full_curve)
        polygon = _flooded_polygon(mask, dem, patch, max_capped_fill)
        dist_km = _haversine_km(dam_lat, dam_lon, sink_lat, sink_lon)
        if dist_km == 0:
            continue

        for direction in ("up", "down"):
            saddle_top = saddle_elev + max_wall_height_m
            if direction == "up":
                fmin = max(sink_elev, dam_elev + min_head_m)
                fmax = saddle_top
            else:
                fmin = sink_elev
                fmax = min(saddle_top, dam_elev - min_head_m)
            if fmax <= fmin + 1.0:
                continue

            head_at_fmax = (fmax - dam_elev) if direction == "up" else (dam_elev - fmax)
            if head_at_fmax < min_head_m:
                continue
            if (dist_km * 1000) / head_at_fmax > max_ratio:
                continue

            curve = [s for s in full_curve if fmin <= s["fill_m"] <= fmax]
            if not curve:
                continue
            max_volume_m3 = max(s["volume_m3"] for s in curve)
            if max_volume_m3 <= 0:
                continue

            candidates.append({
                "direction": direction,
                "sink_lat": sink_lat,
                "sink_lon": sink_lon,
                "sink_elevation_m": sink_elev,
                "saddle_elevation_m": saddle_elev,
                "saddle_width_m": saddle["width_m"],
                "centroid_lat": centroid_lat,
                "centroid_lon": centroid_lon,
                "footprint_polygon": polygon,
                "distance_km": dist_km,
                "area_fill_curve": curve,
                "max_volume_m3": max_volume_m3,
                "existing_dam_role": "lower" if direction == "up" else "upper",
                "basin_capped": basin_capped,
            })

    candidates.sort(key=lambda c: -c["max_volume_m3"])
    return [{k: v for k, v in c.items() if k != "max_volume_m3"} for c in candidates[:max_basins]]
