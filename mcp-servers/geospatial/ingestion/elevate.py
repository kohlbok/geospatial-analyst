import logging
import math
from pathlib import Path

import numpy as np
import requests

from ..config import DATA_GEOSPATIAL, get_bbox

log = logging.getLogger(__name__)

SRTM_BASE_URL = "https://elevation-tiles-prod.s3.amazonaws.com/skadi"
OPEN_TOPO_URL = "https://portal.opentopography.org/API/globaldem"


def _srtm_tile_name(lat, lon):
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{ns}{abs(int(math.floor(lat))):02d}{ew}{abs(int(math.floor(lon))):03d}"


def _download_srtm_tile(tile_name):
    tile_dir = DATA_GEOSPATIAL / "srtm"
    tile_dir.mkdir(parents=True, exist_ok=True)
    hgt_path = tile_dir / f"{tile_name}.hgt"

    if hgt_path.exists():
        return hgt_path

    gz_path = tile_dir / f"{tile_name}.hgt.gz"
    if not gz_path.exists():
        ns_dir = tile_name[:3]
        url = f"{SRTM_BASE_URL}/{ns_dir}/{tile_name}.hgt.gz"
        log.info(f"Downloading SRTM tile: {tile_name}")
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            with open(gz_path, "wb") as f:
                f.write(resp.content)
        except Exception as e:
            log.warning(f"Failed to download SRTM tile {tile_name}: {e}")
            return None

    import gzip
    try:
        with gzip.open(gz_path, "rb") as gz:
            with open(hgt_path, "wb") as out:
                out.write(gz.read())
        gz_path.unlink(missing_ok=True)
        return hgt_path
    except Exception as e:
        log.warning(f"Failed to decompress {tile_name}: {e}")
        return None


def _read_hgt(hgt_path, lat, lon):
    data = np.fromfile(str(hgt_path), dtype=">i2")
    if len(data) == 3601 * 3601:
        size = 3601
    elif len(data) == 1201 * 1201:
        size = 1201
    else:
        return None

    data = data.reshape((size, size))
    tile_lat = int(math.floor(lat))
    tile_lon = int(math.floor(lon))

    frac_lat = lat - tile_lat
    frac_lon = lon - tile_lon

    row = int((1 - frac_lat) * (size - 1))
    col = int(frac_lon * (size - 1))

    row = max(0, min(row, size - 1))
    col = max(0, min(col, size - 1))

    elev = int(data[row, col])
    if elev == -32768:
        return None
    return elev


_tile_cache = {}


def get_elevation(lat, lon):
    tile_name = _srtm_tile_name(lat, lon)
    if tile_name not in _tile_cache:
        path = _download_srtm_tile(tile_name)
        _tile_cache[tile_name] = path

    path = _tile_cache[tile_name]
    if path is None:
        return _fallback_elevation(lat, lon)

    elev = _read_hgt(path, lat, lon)
    if elev is None:
        return _fallback_elevation(lat, lon)
    return elev


def get_elevation_batch(lats, lons):
    tiles_needed = set()
    for lat, lon in zip(lats, lons):
        tiles_needed.add(_srtm_tile_name(lat, lon))

    for tile_name in tiles_needed:
        if tile_name not in _tile_cache:
            path = _download_srtm_tile(tile_name)
            _tile_cache[tile_name] = path

    elevations = []
    for lat, lon in zip(lats, lons):
        elevations.append(get_elevation(lat, lon))
    return elevations


def _fallback_elevation(lat, lon):
    try:
        url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("results"):
            return data["results"][0].get("elevation")
    except Exception:
        pass
    return None


def predownload_morocco_tiles():
    lat_min, lat_max, lon_min, lon_max = get_bbox()
    tiles = set()
    for lat in range(int(math.floor(lat_min)), int(math.ceil(lat_max))):
        for lon in range(int(math.floor(lon_min)), int(math.ceil(lon_max))):
            tiles.add(_srtm_tile_name(lat, lon))

    log.info(f"Pre-downloading {len(tiles)} SRTM tiles for Morocco")
    success = 0
    for tile_name in sorted(tiles):
        path = _download_srtm_tile(tile_name)
        if path:
            _tile_cache[tile_name] = path
            success += 1
    log.info(f"Downloaded {success}/{len(tiles)} SRTM tiles")
    return success


def enrich_dam_elevations(dam_registry):
    log.info(f"Enriching {len(dam_registry)} dams with SRTM elevation data")
    predownload_morocco_tiles()

    wall_elevations = []
    centroid_elevations = []
    crosscheck_deltas = []

    for _, dam in dam_registry.iterrows():
        lat, lon = dam["lat"], dam["lon"]
        if lat is None or lon is None:
            wall_elevations.append(None)
            centroid_elevations.append(None)
            crosscheck_deltas.append(None)
            continue

        wall_elev = get_elevation(lat, lon)
        wall_elevations.append(wall_elev)

        offset = 0.005
        neighbors = [
            get_elevation(lat + offset, lon),
            get_elevation(lat - offset, lon),
            get_elevation(lat, lon + offset),
            get_elevation(lat, lon - offset),
        ]
        valid_neighbors = [e for e in neighbors if e is not None]
        centroid_elev = int(np.mean(valid_neighbors)) if valid_neighbors else wall_elev
        centroid_elevations.append(centroid_elev)

        db_elev = dam.get("elevation_db_m")
        if wall_elev is not None and db_elev is not None:
            delta = abs(wall_elev - db_elev)
            crosscheck_deltas.append(delta)
            if delta > 20:
                log.warning(
                    f"Elevation discrepancy for {dam['name']}: "
                    f"SRTM={wall_elev}m, DB={db_elev}m, delta={delta}m"
                )
        else:
            crosscheck_deltas.append(None)

    dam_registry = dam_registry.copy()
    dam_registry["elevation_wall_m"] = wall_elevations
    dam_registry["elevation_centroid_m"] = centroid_elevations
    dam_registry["elevation_source"] = "srtm30"
    dam_registry["elevation_crosscheck_delta_m"] = crosscheck_deltas

    missing = dam_registry["elevation_wall_m"].isna().sum()
    if missing > 0:
        log.warning(f"{missing} dams missing SRTM elevation data")

    return dam_registry
