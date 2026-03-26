import io
import logging
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

from ..config import DATA_RAW, get_bbox

log = logging.getLogger(__name__)

GRAND_URLS = [
    "https://ln.sync.com/dl/d35a65460/view/default/6957506820004",
    "https://sedac.ciesin.columbia.edu/downloads/data/grand-v1/grand-v1-dams-rev01/dams-rev01-global-shp.zip",
]

GEODAR_ZENODO_URL = "https://zenodo.org/api/records/6163413/files/GeoDAR_v10_v11.zip/content"

HYDROLAKES_URL = "https://data.hydrosheds.org/file/HydroLAKES/HydroLAKES_polys_v10_shp.zip"

FAO_AQUASTAT_URLS = [
    "https://data.apps.fao.org/aquastat/data/csv/aquastat_dams.csv",
    "https://storage.googleapis.com/fao-aquastat-public/Data/csv/aquastat_dams.csv",
]


def _download_file(url, dest, description="file"):
    if dest.exists():
        log.info(f"{description} already cached at {dest}")
        return True
    log.info(f"Downloading {description} from {url}")
    try:
        resp = requests.get(url, timeout=300, stream=True)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        log.info(f"Downloaded {description} to {dest}")
        return True
    except Exception as e:
        log.warning(f"Failed to download {description}: {e}")
        return False


def _download_and_extract_zip(url, dest_dir, description="archive"):
    dest_dir.mkdir(parents=True, exist_ok=True)
    marker = dest_dir / ".downloaded"
    if marker.exists():
        log.info(f"{description} already extracted at {dest_dir}")
        return True
    log.info(f"Downloading {description} from {url}")
    try:
        resp = requests.get(url, timeout=600, stream=True)
        resp.raise_for_status()
        content = io.BytesIO(resp.content)
        with zipfile.ZipFile(content) as zf:
            zf.extractall(dest_dir)
        marker.touch()
        log.info(f"Extracted {description} to {dest_dir}")
        return True
    except Exception as e:
        log.warning(f"Failed to download {description}: {e}")
        return False


def _find_shapefile(directory):
    for shp in Path(directory).rglob("*.shp"):
        return shp
    return None


def download_grand():
    dest_dir = DATA_RAW / "grand"
    for url in GRAND_URLS:
        if _download_and_extract_zip(url, dest_dir, "GRanD v1.3"):
            return dest_dir
    return None


def download_geodar():
    dest_dir = DATA_RAW / "geodar"
    if _download_and_extract_zip(GEODAR_ZENODO_URL, dest_dir, "GeoDAR"):
        return dest_dir
    return None


def download_hydrolakes():
    dest_dir = DATA_RAW / "hydrolakes"
    if _download_and_extract_zip(HYDROLAKES_URL, dest_dir, "HydroLAKES"):
        return dest_dir
    return None


def download_fao():
    dest_dir = DATA_RAW / "fao"
    dest_dir.mkdir(parents=True, exist_ok=True)
    csv_path = dest_dir / "aquastat_dams.csv"
    for url in FAO_AQUASTAT_URLS:
        if _download_file(url, csv_path, "FAO AQUASTAT CSV"):
            return dest_dir
    return None


def _filter_bbox(gdf, lat_min, lat_max, lon_min, lon_max):
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    centroids = gdf.geometry.centroid
    mask = (
        (centroids.y >= lat_min)
        & (centroids.y <= lat_max)
        & (centroids.x >= lon_min)
        & (centroids.x <= lon_max)
    )
    return gdf[mask].copy()


def parse_grand(data_dir):
    shp = _find_shapefile(data_dir)
    if not shp:
        log.error("No shapefile found in GRanD directory")
        return None
    log.info(f"Reading GRanD shapefile: {shp}")
    gdf = gpd.read_file(shp)
    lat_min, lat_max, lon_min, lon_max = get_bbox()
    gdf = _filter_bbox(gdf, lat_min, lat_max, lon_min, lon_max)
    log.info(f"GRanD: {len(gdf)} dams in Morocco bbox")

    records = []
    for _, row in gdf.iterrows():
        centroid = row.geometry.centroid if row.geometry else None
        records.append({
            "source": "grand",
            "source_id": str(row.get("GRAND_ID", "")),
            "name": str(row.get("DAM_NAME", row.get("Dam_name", ""))).strip(),
            "lat": centroid.y if centroid else None,
            "lon": centroid.x if centroid else None,
            "height_m": _safe_float(row.get("DAM_HGT", row.get("Dam_hgt"))),
            "capacity_mcm": _safe_float(row.get("CAP_MCM", row.get("Cap_mcm"))),
            "surface_area_km2": _safe_float(row.get("AREA_SKM", row.get("Area_skm"))),
            "year_built": _safe_int(row.get("YEAR", row.get("Year"))),
            "purpose": str(row.get("USE_IRRI", row.get("Purpose", ""))).strip(),
            "country": str(row.get("COUNTRY", row.get("Country", ""))).strip(),
        })
    return pd.DataFrame(records)


def parse_geodar(data_dir):
    csv_files = list(Path(data_dir).rglob("*.csv"))
    shp_files = list(Path(data_dir).rglob("*.shp"))

    for csv_file in sorted(csv_files, key=lambda f: f.stat().st_size, reverse=True):
        try:
            df = pd.read_csv(csv_file, low_memory=False)
            lat_cols = [c for c in df.columns if "lat" in c.lower()]
            lon_cols = [c for c in df.columns if "lon" in c.lower() or "lng" in c.lower()]
            if not lat_cols or not lon_cols:
                continue
            lat_col = lat_cols[0]
            lon_col = lon_cols[0]
            log.info(f"Reading GeoDAR CSV: {csv_file} ({len(df)} rows, columns: {list(df.columns)[:10]})")

            df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
            df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
            lat_min, lat_max, lon_min, lon_max = get_bbox()
            mask = (
                (df[lat_col] >= lat_min)
                & (df[lat_col] <= lat_max)
                & (df[lon_col] >= lon_min)
                & (df[lon_col] <= lon_max)
            )
            df = df[mask].copy()
            log.info(f"GeoDAR CSV: {len(df)} dams in Morocco bbox")

            if len(df) == 0:
                continue

            name_col = _find_col(df, ["dam_name", "name", "dam", "res_name", "reservoir"])
            height_col = _find_col(df, ["dam_height", "height", "dam_hgt", "dam_h"])
            cap_col = _find_col(df, ["capacity", "cap_mcm", "storage", "vol_mcm", "cap_max", "rv_mcm_v10", "rv_mcm"])
            area_col = _find_col(df, ["area", "surface_area", "area_skm", "res_area"])
            year_col = _find_col(df, ["year", "year_built", "completion", "year_com"])

            records = []
            for _, row in df.iterrows():
                records.append({
                    "source": "geodar",
                    "source_id": str(row.get("id_v11", row.get("GeoDAR_ID", row.get("id", row.get("OBJECTID", ""))))),
                    "name": str(row[name_col]).strip() if name_col and pd.notna(row.get(name_col)) else "",
                    "lat": float(row[lat_col]),
                    "lon": float(row[lon_col]),
                    "height_m": _safe_float(row.get(height_col)) if height_col else None,
                    "capacity_mcm": _safe_float(row.get(cap_col)) if cap_col else None,
                    "surface_area_km2": _safe_float(row.get(area_col)) if area_col else None,
                    "year_built": _safe_int(row.get(year_col)) if year_col else None,
                    "purpose": "",
                    "country": str(row.get("country", row.get("Country", ""))).strip(),
                })
            return pd.DataFrame(records)
        except Exception as e:
            log.warning(f"Failed to read GeoDAR CSV {csv_file}: {e}")
            continue

    for shp in shp_files:
        try:
            log.info(f"Reading GeoDAR shapefile: {shp}")
            lat_min, lat_max, lon_min, lon_max = get_bbox()
            gdf = gpd.read_file(shp, bbox=(lon_min, lat_min, lon_max, lat_max))
            log.info(f"GeoDAR shapefile: {len(gdf)} features in Morocco bbox")

            if len(gdf) == 0:
                continue

            records = []
            for _, row in gdf.iterrows():
                centroid = row.geometry.centroid if row.geometry else None
                name_col = _find_col_gdf(row, ["dam_name", "name", "dam", "res_name"])
                records.append({
                    "source": "geodar",
                    "source_id": str(row.get("GeoDAR_ID", row.get("id", ""))),
                    "name": str(row[name_col]).strip() if name_col else "",
                    "lat": centroid.y if centroid else None,
                    "lon": centroid.x if centroid else None,
                    "height_m": _safe_float(row.get("dam_height", row.get("height"))),
                    "capacity_mcm": _safe_float(row.get("capacity", row.get("cap_mcm"))),
                    "surface_area_km2": _safe_float(row.get("area", row.get("surface_area"))),
                    "year_built": _safe_int(row.get("year", row.get("year_built"))),
                    "purpose": "",
                    "country": "",
                })
            return pd.DataFrame(records)
        except Exception as e:
            log.warning(f"Failed to read GeoDAR shapefile {shp}: {e}")

    log.error("No usable GeoDAR data files found")
    return None


def parse_hydrolakes(data_dir):
    shp = _find_shapefile(data_dir)
    if not shp:
        log.error("No shapefile found in HydroLAKES directory")
        return None
    log.info(f"Reading HydroLAKES shapefile: {shp}")
    lat_min, lat_max, lon_min, lon_max = get_bbox()
    gdf = gpd.read_file(shp, bbox=(lon_min, lat_min, lon_max, lat_max))
    log.info(f"HydroLAKES: {len(gdf)} features in Morocco bbox")

    dam_types = [1, 2, 3]
    type_col = _find_col_from_list(gdf.columns, ["Lake_type", "lake_type", "TYPE", "type"])
    if type_col:
        reservoir_mask = gdf[type_col].isin(dam_types)
        gdf = gdf[reservoir_mask].copy()
        log.info(f"HydroLAKES: {len(gdf)} reservoirs (filtered by type)")

    records = []
    for _, row in gdf.iterrows():
        centroid = row.geometry.centroid if row.geometry else None
        records.append({
            "source": "hydrolakes",
            "source_id": str(row.get("Hylak_id", row.get("HYLAK_ID", ""))),
            "name": str(row.get("Lake_name", row.get("LAKE_NAME", ""))).strip(),
            "lat": centroid.y if centroid else None,
            "lon": centroid.x if centroid else None,
            "height_m": None,
            "capacity_mcm": _vol_to_mcm(row.get("Vol_total", row.get("VOL_TOTAL"))),
            "surface_area_km2": _safe_float(row.get("Lake_area", row.get("LAKE_AREA"))),
            "elevation_m": _safe_float(row.get("Elevation", row.get("ELEVATION"))),
            "shore_len_km": _safe_float(row.get("Shore_len", row.get("SHORE_LEN"))),
            "year_built": None,
            "purpose": "",
            "country": "",
        })
    return pd.DataFrame(records)


def parse_fao(data_dir):
    csv_path = data_dir / "aquastat_dams.csv"
    xlsx_path = data_dir / "AQUASTAT_Dams.xlsx"

    df = None
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path, low_memory=False)
            log.info(f"Reading FAO CSV: {csv_path}")
        except Exception as e:
            log.warning(f"Failed to read FAO CSV: {e}")

    if df is None and xlsx_path.exists():
        try:
            df = pd.read_excel(xlsx_path)
            log.info(f"Reading FAO Excel: {xlsx_path}")
        except Exception as e:
            log.warning(f"Failed to read FAO Excel: {e}")

    if df is None:
        log.error("No FAO AQUASTAT data found")
        return None

    country_col = _find_col_from_list(df.columns, ["Country", "country", "COUNTRY", "Area"])
    if country_col:
        morocco_names = ["Morocco", "Maroc", "MAR", "morocco"]
        df = df[df[country_col].astype(str).str.strip().isin(morocco_names)].copy()
    log.info(f"FAO: {len(df)} dams for Morocco")

    lat_col = _find_col_from_list(df.columns, ["Latitude", "latitude", "lat", "LAT"])
    lon_col = _find_col_from_list(df.columns, ["Longitude", "longitude", "lon", "LON", "lng"])
    name_col = _find_col_from_list(df.columns, ["Dam_name", "dam_name", "Name", "name", "DAM_NAME"])
    height_col = _find_col_from_list(df.columns, ["Dam_height", "height", "Height", "DAM_HEIGHT"])
    cap_col = _find_col_from_list(df.columns, ["Capacity", "capacity", "CAP_MCM", "Reservoir_capacity", "Storage"])
    year_col = _find_col_from_list(df.columns, ["Year", "year", "Year_completed", "Completion"])
    purpose_col = _find_col_from_list(df.columns, ["Purpose", "purpose", "Use", "use", "Main_use"])

    records = []
    for _, row in df.iterrows():
        lat_val = _safe_float(row.get(lat_col)) if lat_col else None
        lon_val = _safe_float(row.get(lon_col)) if lon_col else None
        records.append({
            "source": "fao",
            "source_id": str(row.get("ID", row.get("id", ""))),
            "name": str(row[name_col]).strip() if name_col and pd.notna(row.get(name_col)) else "",
            "lat": lat_val,
            "lon": lon_val,
            "height_m": _safe_float(row.get(height_col)) if height_col else None,
            "capacity_mcm": _safe_float(row.get(cap_col)) if cap_col else None,
            "surface_area_km2": None,
            "year_built": _safe_int(row.get(year_col)) if year_col else None,
            "purpose": str(row[purpose_col]).strip() if purpose_col and pd.notna(row.get(purpose_col)) else "",
            "country": "Morocco",
        })
    return pd.DataFrame(records)


def download_all():
    results = {}
    log.info("Starting database downloads...")

    grand_dir = download_grand()
    if grand_dir:
        results["grand"] = parse_grand(grand_dir)
        if results["grand"] is not None:
            log.info(f"GRanD: parsed {len(results['grand'])} Morocco dams")

    geodar_dir = download_geodar()
    if geodar_dir:
        results["geodar"] = parse_geodar(geodar_dir)
        if results["geodar"] is not None:
            log.info(f"GeoDAR: parsed {len(results['geodar'])} Morocco dams")

    hydrolakes_dir = download_hydrolakes()
    if hydrolakes_dir:
        results["hydrolakes"] = parse_hydrolakes(hydrolakes_dir)
        if results["hydrolakes"] is not None:
            log.info(f"HydroLAKES: parsed {len(results['hydrolakes'])} Morocco features")

    fao_dir = download_fao()
    if fao_dir:
        results["fao"] = parse_fao(fao_dir)
        if results["fao"] is not None:
            log.info(f"FAO: parsed {len(results['fao'])} Morocco dams")

    available = {k: v for k, v in results.items() if v is not None and len(v) > 0}
    if not available:
        _print_manual_instructions()
    else:
        failed = [k for k, v in results.items() if v is None or (v is not None and len(v) == 0)]
        if failed:
            log.warning(f"Failed to load: {failed}. Proceeding with: {list(available.keys())}")

    return available


def _print_manual_instructions():
    instructions = """
=== MANUAL DOWNLOAD REQUIRED ===

Some or all dam databases could not be downloaded automatically.
Please download them manually and place them in the data/raw/ directory:

1. GRanD v1.3:
   - Go to https://www.globaldamwatch.org/grand
   - Download the shapefile package
   - Extract to data/raw/grand/

2. GeoDAR:
   - Go to https://zenodo.org/records/6163413
   - Download GeoDAR_v10_v11.zip
   - Extract to data/raw/geodar/

3. HydroLAKES:
   - Go to https://www.hydrosheds.org/products/hydrolakes
   - Download HydroLAKES_polys_v10_shp.zip
   - Extract to data/raw/hydrolakes/

4. FAO AQUASTAT:
   - Go to https://www.fao.org/aquastat/en/databases/dams
   - Download the dams database (CSV or Excel)
   - Place in data/raw/fao/

After downloading, rerun the ingestion step.
================================
"""
    log.warning(instructions)
    print(instructions)


def _safe_float(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        v = float(val)
        return v if not (v < -1 or v > 1e12) else None
    except (ValueError, TypeError):
        return None


def _safe_int(val):
    if val is None:
        return None
    try:
        v = int(float(val))
        return v if 1000 < v < 2100 else None
    except (ValueError, TypeError):
        return None


def _vol_to_mcm(val):
    v = _safe_float(val)
    if v is None:
        return None
    return v / 1e6 if v > 1e6 else v


def _find_col(df, candidates):
    cols_lower = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in cols_lower:
            return cols_lower[name.lower()]
    return None


def _find_col_gdf(row, candidates):
    keys = row.index.tolist() if hasattr(row, "index") else list(row.keys())
    keys_lower = {k.lower(): k for k in keys}
    for name in candidates:
        if name.lower() in keys_lower:
            return keys_lower[name.lower()]
    return None


def _find_col_from_list(columns, candidates):
    cols_lower = {c.lower(): c for c in columns}
    for name in candidates:
        if name.lower() in cols_lower:
            return cols_lower[name.lower()]
    return None
