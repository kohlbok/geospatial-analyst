import json
import logging
import math
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

STAGING_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "raw" / "staging"
MANIFEST_PATH = STAGING_DIR / "_sources_manifest.json"


def _ensure_staging():
    STAGING_DIR.mkdir(parents=True, exist_ok=True)


def save_staged_source(name, records, source_metadata=None):
    _ensure_staging()

    out_path = STAGING_DIR / f"{name}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, default=str, ensure_ascii=False)

    manifest = _load_manifest()
    manifest[name] = {
        "file": f"{name}.json",
        "record_count": len(records),
        "retrieved": datetime.now().isoformat(),
        **(source_metadata or {}),
    }
    _save_manifest(manifest)

    log.info(f"Staged {len(records)} records as '{name}' -> {out_path}")
    return {
        "name": name,
        "path": str(out_path),
        "record_count": len(records),
    }


def list_staged_sources():
    _ensure_staging()
    manifest = _load_manifest()

    sources = []
    for name, meta in manifest.items():
        file_path = STAGING_DIR / meta["file"]
        if not file_path.exists():
            continue

        with open(file_path, encoding="utf-8") as f:
            records = json.load(f)

        def _has(r, field):
            v = r.get(field)
            if v is None:
                return False
            if isinstance(v, float) and math.isnan(v):
                return False
            return True

        stats = {
            "name": name,
            "record_count": len(records),
            "has_coords": sum(1 for r in records if _has(r, "lat") and _has(r, "lon")),
            "has_name": sum(1 for r in records if _has(r, "name")),
            "has_height": sum(1 for r in records if _has(r, "height_m")),
            "has_capacity": sum(1 for r in records if _has(r, "capacity_mcm")),
            "fields_present": sorted(set().union(*(r.keys() for r in records))) if records else [],
            "retrieved": meta.get("retrieved"),
        }
        sources.append(stats)

    return sources


def read_staged_source(name, offset=0, limit=50):
    file_path = STAGING_DIR / f"{name}.json"
    if not file_path.exists():
        return {"error": f"Staged source not found: {name}"}

    with open(file_path, encoding="utf-8") as f:
        records = json.load(f)

    sliced = records[offset:offset + limit]
    return {
        "name": name,
        "total_records": len(records),
        "offset": offset,
        "returned": len(sliced),
        "records": sliced,
    }


def load_all_staged():
    _ensure_staging()
    manifest = _load_manifest()
    sources = {}
    for name, meta in manifest.items():
        file_path = STAGING_DIR / meta["file"]
        if file_path.exists():
            with open(file_path, encoding="utf-8") as f:
                sources[name] = json.load(f)
    return sources


def _load_manifest():
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_manifest(manifest):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
