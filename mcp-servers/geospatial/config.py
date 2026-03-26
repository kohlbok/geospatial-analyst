import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "parameters.json"
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_GEOSPATIAL = PROJECT_ROOT / "data" / "geospatial"
OUTPUT_MAPS = PROJECT_ROOT / "output" / "maps"
OUTPUT_REPORTS = PROJECT_ROOT / "output" / "reports"
OUTPUT_EXPORTS = PROJECT_ROOT / "output" / "exports"

for d in [DATA_RAW, DATA_PROCESSED, DATA_GEOSPATIAL, OUTPUT_MAPS, OUTPUT_REPORTS, OUTPUT_EXPORTS]:
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


def get_bbox():
    cfg = load_config()
    bb = cfg["morocco_bbox"]
    return bb["lat_min"], bb["lat_max"], bb["lon_min"], bb["lon_max"]


def get_screening_params(variant="standard"):
    cfg = load_config()
    if variant == "standard":
        return cfg["screening"]
    return cfg["sensitivity"].get(variant, cfg["screening"])


def get_scoring_weights(variant="default"):
    cfg = load_config()
    key = f"weights_{variant}"
    return cfg["scoring"].get(key, cfg["scoring"]["weights_default"])
