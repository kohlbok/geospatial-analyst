import json
import logging
from pathlib import Path

import pandas as pd

from .inspect import detect_format

log = logging.getLogger(__name__)

STAGING_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "raw" / "staging"


def parse_tabular(path, column_mapping, filters=None, output_name="parsed"):
    path = Path(path)
    if not path.exists():
        return {"error": f"File not found: {path}"}

    fmt = detect_format(path)
    df = _read_file(path, fmt)
    if df is None:
        return {"error": f"Could not read file: {path}"}

    log.info(f"Read {len(df)} rows from {path.name}")

    if filters:
        df = _apply_filters(df, filters)
        log.info(f"After filtering: {len(df)} rows")

    if not column_mapping:
        return {"error": "column_mapping is required"}

    records = _apply_mapping(df, column_mapping)

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    out_path = STAGING_DIR / f"{output_name}.json"
    with open(out_path, "w") as f:
        json.dump(records, f, indent=2, default=str)

    has_coords = sum(1 for r in records if r.get("lat") is not None and r.get("lon") is not None)
    has_name = sum(1 for r in records if r.get("name"))

    log.info(f"Parsed {len(records)} records -> {out_path}")
    return {
        "output_path": str(out_path),
        "record_count": len(records),
        "has_coords": has_coords,
        "has_name": has_name,
        "sample": records[:3] if records else [],
    }


def _read_file(path, fmt):
    try:
        if fmt == "csv":
            for enc in ["utf-8-sig", "utf-8", "latin-1"]:
                try:
                    return pd.read_csv(path, encoding=enc, low_memory=False)
                except UnicodeDecodeError:
                    continue
        elif fmt in ("xlsx", "xls"):
            df = pd.read_excel(path, sheet_name=0)
            if len(df) > 0 and df.iloc[0].astype(str).str.contains("name|dam|country|lat", case=False).any():
                new_cols = df.iloc[0].astype(str).tolist()
                df = df.iloc[1:].reset_index(drop=True)
                df.columns = new_cols
            return df
        elif fmt == "shapefile":
            import geopandas as gpd
            return gpd.read_file(path)
        elif fmt in ("geojson", "geopackage"):
            import geopandas as gpd
            return gpd.read_file(path)
        elif fmt == "json":
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                return pd.DataFrame(data)
            for key in ["features", "dams", "records", "data"]:
                if key in data and isinstance(data[key], list):
                    return pd.DataFrame(data[key])
            return pd.DataFrame([data])
    except Exception as e:
        log.error(f"Failed to read {path}: {e}")
    return None


def _apply_filters(df, filters):
    for filt in filters:
        ftype = filt.get("type", "eq")

        if ftype == "eq":
            col = filt["column"]
            val = filt["value"]
            if col in df.columns:
                df = df[df[col].astype(str).str.strip().str.lower() == str(val).lower()].copy()

        elif ftype == "contains":
            col = filt["column"]
            val = filt["value"]
            if col in df.columns:
                df = df[df[col].astype(str).str.contains(val, case=False, na=False)].copy()

        elif ftype == "bbox":
            lat_col = filt["lat_col"]
            lon_col = filt["lon_col"]
            bbox = filt["bbox"]
            if lat_col in df.columns and lon_col in df.columns:
                df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
                df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
                df = df[
                    (df[lat_col] >= bbox[0]) & (df[lat_col] <= bbox[1]) &
                    (df[lon_col] >= bbox[2]) & (df[lon_col] <= bbox[3])
                ].copy()

        elif ftype == "notnull":
            col = filt["column"]
            if col in df.columns:
                df = df[df[col].notna()].copy()

    return df


def _apply_mapping(df, column_mapping):
    records = []
    for _, row in df.iterrows():
        record = {}
        for src_col, dst_field in column_mapping.items():
            if src_col not in df.columns:
                record[dst_field] = None
                continue
            val = row[src_col]
            if pd.isna(val):
                record[dst_field] = None
            elif dst_field in ("lat", "lon", "height_m", "capacity_mcm", "surface_area_km2",
                               "elevation_m", "depth_m", "shore_len_km", "catchment_km2"):
                try:
                    record[dst_field] = float(val)
                except (ValueError, TypeError):
                    record[dst_field] = None
            elif dst_field in ("year_built",):
                try:
                    record[dst_field] = int(float(val))
                except (ValueError, TypeError):
                    record[dst_field] = None
            else:
                record[dst_field] = str(val).strip()
        records.append(record)
    return records
