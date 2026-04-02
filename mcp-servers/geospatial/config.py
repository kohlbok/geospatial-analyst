import json
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "parameters.json"

DATA_DIR = PROJECT_ROOT / "data"

DATA_CACHE = PROJECT_ROOT / "data" / ".cache"
DATA_RAW = DATA_CACHE / "raw"
DATA_PROCESSED = DATA_CACHE / "intermediate"
DATA_GEOSPATIAL = DATA_CACHE / "srtm"

OUTPUT_DIR = PROJECT_ROOT / "output"

log = logging.getLogger(__name__)

for d in [DATA_RAW, DATA_PROCESSED, DATA_GEOSPATIAL, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

_config_cache = None
_boundary_cache = None
_active_file = None

NATURAL_EARTH_URL = "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"


def load_config():
    global _config_cache
    if _config_cache is None:
        with open(CONFIG_PATH) as f:
            _config_cache = json.load(f)
    return _config_cache


def reload_config():
    global _config_cache
    _config_cache = None
    return load_config()


def get_country_boundary():
    global _boundary_cache
    if _boundary_cache is not None:
        return _boundary_cache

    import geopandas as gpd

    cfg = load_config()
    country = cfg.get("country", "")

    cache_dir = DATA_RAW / "naturalearth"
    cache_dir.mkdir(parents=True, exist_ok=True)
    shp_path = cache_dir / "ne_110m_admin_0_countries.shp"

    if not shp_path.exists():
        from .ingestion.download import _download_and_extract_zip
        log.info("Downloading Natural Earth country boundaries...")
        _download_and_extract_zip(NATURAL_EARTH_URL, cache_dir, "Natural Earth boundaries")

    if not shp_path.exists():
        shp_files = list(cache_dir.rglob("*.shp"))
        shp_path = shp_files[0] if shp_files else None

    if shp_path is None or not shp_path.exists():
        log.warning("Could not load Natural Earth boundaries")
        return None

    world = gpd.read_file(shp_path)
    match = world[world["NAME"].str.lower() == country.lower()]
    if match.empty:
        match = world[world["NAME_LONG"].str.lower() == country.lower()]
    if match.empty:
        match = world[world["ISO_A3"].str.lower() == country.lower()]
    if match.empty:
        match = world[world["ADMIN"].str.lower() == country.lower()]

    if match.empty:
        log.warning(f"Country '{country}' not found in Natural Earth data")
        return None

    _boundary_cache = match.iloc[0].geometry
    log.info(f"Loaded boundary for {country}")
    return _boundary_cache


def get_bbox():
    boundary = get_country_boundary()
    if boundary is not None:
        minx, miny, maxx, maxy = boundary.bounds
        return miny, maxy, minx, maxx

    cfg = load_config()
    bb = cfg.get("bbox", [-90, 90, -180, 180])
    return bb[0], bb[1], bb[2], bb[3]


def list_data_files():
    files = []
    for ext in ("*.json", "*.xlsx", "*.csv"):
        for p in DATA_DIR.glob(ext):
            if p.name.startswith("."):
                continue
            files.append(p.name)
    return sorted(files)


def set_active_file(filename):
    global _active_file
    path = DATA_DIR / filename
    if not path.exists():
        return None
    if path.suffix in (".xlsx", ".csv"):
        json_path = path.with_suffix(".json")
        if not json_path.exists():
            return "needs_parsing"
        _active_file = json_path
        return json_path
    _active_file = path
    return path


def get_active_file():
    return _active_file


def _save_json(dams, path):
    import math
    cleaned = []
    for dam in dams:
        clean = {}
        for k, v in dam.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                clean[k] = None
            else:
                clean[k] = v
        cleaned.append(clean)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(cleaned, f, indent=2)


def load_dams():
    if _active_file is None or not _active_file.exists():
        return None
    with open(_active_file) as f:
        return json.load(f)


def save_dams(dams):
    if _active_file is None:
        return
    _save_json(dams, _active_file)
