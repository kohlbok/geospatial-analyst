import logging
import math

import numpy as np

from ..ingestion.elevate import _download_srtm_tile, _srtm_tile_name

log = logging.getLogger(__name__)

SRTM1_SIZE = 3601
SRTM3_SIZE = 1201


def _tile_resolution(size):
    if size == SRTM1_SIZE:
        return 1.0 / (SRTM1_SIZE - 1)
    return 1.0 / (SRTM3_SIZE - 1)


def _read_hgt_full(hgt_path):
    data = np.fromfile(str(hgt_path), dtype=">i2")
    if len(data) == SRTM1_SIZE * SRTM1_SIZE:
        size = SRTM1_SIZE
    elif len(data) == SRTM3_SIZE * SRTM3_SIZE:
        size = SRTM3_SIZE
    else:
        return None, None
    data = data.reshape((size, size)).astype(np.float32)
    data[data == -32768] = np.nan
    return data, size


def load_dem_patch(center_lat, center_lon, radius_km, resolution_m=90):
    deg_per_km = 1.0 / 111.0
    margin_deg = radius_km * deg_per_km * 1.2

    lat_min = center_lat - margin_deg
    lat_max = center_lat + margin_deg
    lon_min = center_lon - margin_deg
    lon_max = center_lon + margin_deg

    tile_lats = range(int(math.floor(lat_min)), int(math.ceil(lat_max)))
    tile_lons = range(int(math.floor(lon_min)), int(math.ceil(lon_max)))

    tile_data = {}
    for tlat in tile_lats:
        for tlon in tile_lons:
            name = _srtm_tile_name(tlat + 0.5, tlon + 0.5)
            path = _download_srtm_tile(name)
            if path is None or not path.exists():
                continue
            arr, size = _read_hgt_full(path)
            if arr is None:
                continue
            tile_data[(tlat, tlon)] = (arr, size)

    if not tile_data:
        return None

    sizes = [s for _, (_, s) in tile_data.items()]
    native_size = max(sizes)
    native_res_deg = _tile_resolution(native_size)

    if resolution_m >= 80:
        step = 3
    else:
        step = 1

    rows_per_deg = int(round(1.0 / native_res_deg))
    rows_needed = int((lat_max - lat_min) * rows_per_deg / step) + 2
    cols_needed = int((lon_max - lon_min) * rows_per_deg / step) + 2

    patch = np.full((rows_needed, cols_needed), np.nan, dtype=np.float32)

    for row_idx in range(rows_needed):
        lat = lat_max - row_idx * step * native_res_deg
        for col_idx in range(cols_needed):
            lon = lon_min + col_idx * step * native_res_deg
            tlat = int(math.floor(lat))
            tlon = int(math.floor(lon))
            if (tlat, tlon) not in tile_data:
                continue
            arr, size = tile_data[(tlat, tlon)]
            res = _tile_resolution(size)
            frac_lat = lat - tlat
            frac_lon = lon - tlon
            r = int((1.0 - frac_lat) / res)
            c = int(frac_lon / res)
            r = max(0, min(r, size - 1))
            c = max(0, min(c, size - 1))
            patch[row_idx, col_idx] = arr[r, c]

    actual_lat_res = step * native_res_deg
    actual_lon_res = step * native_res_deg

    return {
        "data": patch,
        "lat_min": lat_min,
        "lat_max": lat_max,
        "lon_min": lon_min,
        "lon_max": lon_max,
        "lat_res": actual_lat_res,
        "lon_res": actual_lon_res,
        "rows": rows_needed,
        "cols": cols_needed,
    }


def pixel_to_latlon(row, col, patch):
    lat = patch["lat_max"] - row * patch["lat_res"]
    lon = patch["lon_min"] + col * patch["lon_res"]
    return lat, lon
