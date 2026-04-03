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
        has_country_filter = any(f.get("type") == "country" for f in filters)
        if fmt == "shapefile" and df is not None and has_country_filter:
            from ..config import get_bbox
            lat_min, lat_max, lon_min, lon_max = get_bbox()
            import geopandas as gpd
            df = gpd.read_file(path, bbox=(lon_min, lat_min, lon_max, lat_max))
            log.info(f"Re-read shapefile with country bbox: {len(df)} rows")
        df = _apply_filters(df, filters)
        log.info(f"After filtering: {len(df)} rows")

    if not column_mapping:
        return {"error": "column_mapping is required"}

    from ..config import scrub_nan

    records = scrub_nan(_apply_mapping(df, column_mapping))

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    out_path = STAGING_DIR / f"{output_name}.json"
    with open(out_path, "w") as f:
        json.dump(records, f, indent=2, default=str)

    from .staging import save_staged_source
    save_staged_source(output_name, records)

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
            from .inspect import _find_header_row
            raw = pd.read_excel(path, sheet_name=0, header=None, nrows=30)
            header_row = _find_header_row(raw)
            df = pd.read_excel(path, sheet_name=0, header=header_row)
            df = df.dropna(how="all")
            df = df.loc[:, df.columns.notna()]
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

        elif ftype == "in":
            col = filt["column"]
            values = filt["values"]
            if col in df.columns:
                df = df[df[col].isin(values)].copy()

        elif ftype == "country":
            lat_col = filt.get("lat_col", "lat")
            lon_col = filt.get("lon_col", "lon")
            from ..config import get_country_boundary
            boundary = get_country_boundary()
            if boundary is not None and lat_col in df.columns and lon_col in df.columns:
                from shapely.geometry import Point
                df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
                df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
                mask = df.apply(
                    lambda r: boundary.contains(Point(r[lon_col], r[lat_col]))
                    if pd.notna(r[lat_col]) and pd.notna(r[lon_col]) else False,
                    axis=1,
                )
                df = df[mask].copy()
                log.info(f"Country boundary filter: {len(df)} rows inside boundary")

    return df


NUMERIC_FIELDS = {
    "lat", "lon", "height_m", "capacity_mcm", "surface_area_km2",
    "elevation_m", "depth_m", "shore_len_km", "catchment_km2",
    "grid_distance_km", "fill_rate_pct",
}

INT_FIELDS = {"year_built"}


def _apply_mapping(df, column_mapping):
    mapped_src_cols = set(column_mapping.keys())
    unmapped_cols = [c for c in df.columns if c not in mapped_src_cols]

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
            elif dst_field in NUMERIC_FIELDS:
                try:
                    record[dst_field] = float(val)
                except (ValueError, TypeError):
                    record[dst_field] = None
            elif dst_field in INT_FIELDS:
                try:
                    record[dst_field] = int(float(val))
                except (ValueError, TypeError):
                    record[dst_field] = None
            else:
                record[dst_field] = str(val).strip()

        for col in unmapped_cols:
            val = row[col]
            if pd.isna(val):
                continue
            key = _clean_key(col)
            if not key:
                continue
            if isinstance(val, float) and val == int(val):
                record[key] = int(val)
            else:
                record[key] = val

        records.append(record)
    return records


def _clean_key(col_name):
    import re
    s = str(col_name).strip()
    s = re.sub(r'[()/%]', '', s)
    s = re.sub(r'[^a-zA-Z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_').lower()
    return s
