import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "parameters.json"

DAMS_INPUT = PROJECT_ROOT / "data" / "dams.json"

DATA_CACHE = PROJECT_ROOT / "data" / ".cache"
DATA_RAW = DATA_CACHE / "raw"
DATA_PROCESSED = DATA_CACHE / "intermediate"
DATA_GEOSPATIAL = DATA_CACHE / "srtm"

OUTPUT_DIR = PROJECT_ROOT / "output"

for d in [DATA_RAW, DATA_PROCESSED, DATA_GEOSPATIAL, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

_config_cache = None


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


def get_bbox(country_code=None):
    cfg = load_config()
    bb = cfg.get("bbox", [27.0, 36.0, -13.0, -1.0])
    return bb[0], bb[1], bb[2], bb[3]


def load_dams():
    if not DAMS_INPUT.exists():
        return None
    with open(DAMS_INPUT) as f:
        return json.load(f)
