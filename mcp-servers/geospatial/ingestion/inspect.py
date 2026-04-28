import json
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def detect_format(path):
    path = Path(path)
    suffix = path.suffix.lower()
    format_map = {
        ".csv": "csv",
        ".tsv": "csv",
        ".xlsx": "xlsx",
        ".xls": "xls",
        ".shp": "shapefile",
        ".geojson": "geojson",
        ".json": "json",
        ".gpkg": "geopackage",
    }
    return format_map.get(suffix, "unknown")


def inspect_file(path, max_rows=20):
    path = Path(path)
    if not path.exists():
        return {"error": f"File not found: {path}"}

    fmt = detect_format(path)
    result = {
        "path": str(path),
        "format": fmt,
        "size_bytes": path.stat().st_size,
    }

    try:
        if fmt == "csv":
            result.update(_inspect_csv(path, max_rows))
        elif fmt in ("xlsx", "xls"):
            result.update(_inspect_excel(path, max_rows))
        elif fmt == "shapefile":
            result.update(_inspect_shapefile(path, max_rows))
        elif fmt in ("geojson", "json"):
            result.update(_inspect_json(path, max_rows))
        elif fmt == "geopackage":
            result.update(_inspect_shapefile(path, max_rows))
        else:
            result["error"] = f"Unsupported format: {fmt}"
    except Exception as e:
        result["error"] = str(e)

    return result


def _inspect_csv(path, max_rows):
    for encoding in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            df = pd.read_csv(path, nrows=max_rows, encoding=encoding, low_memory=False)
            total = sum(1 for _ in open(path, encoding=encoding)) - 1
            return _df_summary(df, total)
        except (UnicodeDecodeError, Exception):
            continue
    return {"error": "Could not read CSV with any encoding"}


def _inspect_excel(path, max_rows):
    xls = pd.ExcelFile(path)
    sheets = xls.sheet_names
    result = {"sheets": sheets}

    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=30)

    header_row = _find_header_row(raw)
    result["header_row"] = header_row

    df = pd.read_excel(path, sheet_name=0, header=header_row)
    df = df.dropna(how="all")
    df = df.loc[:, df.columns.notna()]

    result.update(_df_summary(df.head(max_rows), len(df)))
    return result


def _find_header_row(raw):
    keywords = {"name", "dam", "lat", "lon", "height", "capacity", "id", "status", "region", "country", "longitude", "latitude"}
    best_row = 0
    best_score = 0
    for i in range(min(20, len(raw))):
        row_vals = [str(v).strip().lower() for v in raw.iloc[i] if pd.notna(v)]
        score = sum(1 for v in row_vals if any(kw in v for kw in keywords))
        if score > best_score:
            best_score = score
            best_row = i
    return best_row


def _inspect_shapefile(path, max_rows):
    import geopandas as gpd
    gdf = gpd.read_file(path, rows=max_rows)
    total_gdf = gpd.read_file(path)
    result = _df_summary(gdf, len(total_gdf))
    result["crs"] = str(gdf.crs) if gdf.crs else None
    result["geometry_type"] = gdf.geometry.geom_type.unique().tolist() if "geometry" in gdf.columns else None
    return result


def _inspect_json(path, max_rows):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        for key in ["features", "dams", "records", "data", "results"]:
            if key in data and isinstance(data[key], list):
                records = data[key]
                break
        else:
            return {"structure": "dict", "keys": list(data.keys()), "note": "Not a record list"}
    else:
        return {"structure": type(data).__name__}

    df = pd.DataFrame(records[:max_rows])
    return _df_summary(df, len(records))


def _df_summary(df, total_rows):
    columns = []
    for col in df.columns:
        if col == "geometry":
            columns.append({"name": col, "dtype": "geometry", "nulls": 0})
            continue
        columns.append({
            "name": str(col),
            "dtype": str(df[col].dtype),
            "nulls": int(df[col].isna().sum()),
            "sample_values": [str(v) for v in df[col].dropna().head(3).tolist()],
        })

    sample_rows = []
    for _, row in df.head(5).iterrows():
        record = {}
        for col in df.columns:
            if col == "geometry":
                continue
            val = row[col]
            record[str(col)] = None if pd.isna(val) else str(val)
        sample_rows.append(record)

    return {
        "total_rows": total_rows,
        "sample_rows_shown": len(sample_rows),
        "columns": columns,
        "sample_rows": sample_rows,
    }
