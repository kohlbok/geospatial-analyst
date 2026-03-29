import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from ...config import DATA_RAW, get_bbox
from ..download import _download_file, _download_and_extract_zip

log = logging.getLogger(__name__)

FAO_MOROCCO_URL = "https://www.fao.org/nr/water/aquastat/dams/country/MAR-dams_eng.xlsx"
FAO_AFRICA_URL = "https://storage.googleapis.com/fao-maps-catalog-data/geonetwork/aquamaps/african_dams.xls"
GEODAR_ZENODO_URL = "https://zenodo.org/api/records/6163413/files/GeoDAR_v10_v11.zip/content"
HYDROLAKES_URL = "https://data.hydrosheds.org/file/HydroLAKES/HydroLAKES_polys_v10_shp.zip"

FAO_TO_GRAND_ALIASES = {
    "Ahmed Al Hansali": "Dchar El Oued",
    "Oued Martil": "Wadi Martil",
    "Ouljet Essoltane": "Ouljet Es Soltane",
}

KNOWN_COORDINATES = {
    "Al Wahda": (34.5940, -5.1932),
    "Sidi Said": (32.7938, -4.7692),
    "Hassan II": (32.01, -3.68),
    "Sidi Chahed": (34.08, -5.30),
    "Dar Khrofa": (35.03, -5.63),
    "M'dez": (33.98, -4.28),
    "Neuf Avril 1947": (34.23, -2.17),
    "Sahla": (34.80, -4.53),
    "Bouhouda": (34.55, -4.52),
    "Saquia Al Hamra": (27.16, -13.18),
    "Touizgui Rem": (30.12, -6.53),
    "El Maleh": (33.10, -8.10),
    "Yaacoub El Mansour": (33.79, -5.85),
    "Zerrar": (31.22, -9.28),
    "Tamesna": (34.10, -4.16),
    "Mokhtar Soussi": (30.36, -8.42),
    "Tamalout": (32.49, -5.15),
    "Smir": (35.72, -5.36),
    "Bab Louta": (34.19, -4.09),
    "Koudiat El Garn": (34.18, -4.78),
    "Moulay Hassan Bel Medhi": (33.47, -4.34),
    "Tanger Med": (35.80, -5.50),
    "Taskourt": (31.39, -8.47),
    "Sfeissif": (30.75, -7.29),
    "Sidi Mohamed Ben Slimane El Jazouli": (30.54, -9.08),
    "Al Himer": (33.39, -3.74),
    "Timkit": (32.19, -5.70),
    "Ait Messaoud": (31.60, -7.54),
    "Mazer": (34.02, -5.05),
    "Imin El Kheng": (30.82, -8.78),
    "Injil": (34.58, -3.87),
    "Moulay Boucheta": (35.28, -5.21),
    "Sidi Yahya": (34.37, -2.62),
    "Joumouaa": (34.74, -5.00),
    "Sidi Abdellah": (33.68, -6.79),
    "Sehb El Merga": (34.02, -5.42),
    "Ahl Souss": (30.48, -9.13),
    "Draa El Grara": (32.27, -7.38),
    "Krayma": (35.80, -5.45),
    "Douiss Figuig": (32.11, -1.23),
    "Ait Moulay Ahmed": (31.97, -5.94),
    "Essaf": (33.67, -4.42),
    "Aggay": (30.87, -6.69),
    "Sidi El Mahjoub": (34.65, -5.60),
    "Lahouar": (35.10, -4.28),
    "Takhzrit": (31.54, -7.92),
    "El Handak": (34.05, -5.30),
    "Saboun": (35.66, -5.67),
    "Bouknadel": (34.12, -6.73),
    "Gharbia": (35.30, -5.52),
    "Hassar": (33.55, -7.59),
    "Daourat": (32.10, -6.83),
    "Roknet Ennam": (32.20, -3.10),
    "Arabat": (34.95, -4.05),
    "Chbika": (30.92, -8.86),
    "Boubagra": (31.78, -6.07),
    "Oued Namous": (32.38, -3.65),
}


def download_fao():
    dest_dir = DATA_RAW / "fao"
    dest_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = dest_dir / "MAR-dams_eng.xlsx"
    if _download_file(FAO_MOROCCO_URL, xlsx_path, "FAO Morocco dams"):
        return xlsx_path
    xls_path = dest_dir / "african_dams.xls"
    if _download_file(FAO_AFRICA_URL, xls_path, "FAO Africa dams (fallback)"):
        return xls_path
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


def parse_fao(path):
    if path is None or not path.exists():
        log.error("FAO file not found")
        return None

    if path.name.endswith(".xlsx"):
        df = pd.read_excel(path, header=0)
        df = df.iloc[1:].reset_index(drop=True)
        df.columns = [
            "country", "name", "alt_name", "iso", "admin_unit", "nearest_city",
            "river", "major_basin", "sub_basin", "year_completed",
            "height_m", "capacity_mcm", "area_km2", "sedimentation_pct",
            "use_irrigation", "use_water_supply", "use_flood_control", "use_hydropower_mw",
            "use_navigation", "use_recreation", "use_pollution_ctrl", "use_livestock", "use_other",
            "lat", "lon", "national_ref", "other_ref", "comments",
        ]
    else:
        df = pd.read_excel(path)
        country_col = next((c for c in df.columns if "country" in c.lower()), None)
        if country_col:
            df = df[df[country_col].astype(str).str.contains("Morocco|Maroc", case=False, na=False)].copy()
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    for col in ["lat", "lon", "height_m", "capacity_mcm", "area_km2"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "year_completed" in df.columns:
        df["year_completed"] = pd.to_numeric(df["year_completed"], errors="coerce").astype("Int64")

    purposes = []
    use_cols = [c for c in df.columns if c.startswith("use_")]
    for _, row in df.iterrows():
        p = []
        for uc in use_cols:
            val = row.get(uc)
            if pd.notna(val) and str(val).strip() not in ("", "NaN", "nan"):
                label = uc.replace("use_", "")
                if label == "hydropower_mw":
                    p.append(f"hydropower ({val} MW)" if str(val).replace(".", "").isdigit() else "hydropower")
                else:
                    p.append(label)
        purposes.append(p)
    df["purpose"] = purposes

    records = []
    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if not name or name.lower() in ("nan", "none"):
            continue
        records.append({
            "name": name,
            "alt_name": str(row.get("alt_name", "")).strip() if pd.notna(row.get("alt_name")) else None,
            "lat": row.get("lat") if pd.notna(row.get("lat")) else None,
            "lon": row.get("lon") if pd.notna(row.get("lon")) else None,
            "height_m": row.get("height_m") if pd.notna(row.get("height_m")) else None,
            "capacity_mcm": row.get("capacity_mcm") if pd.notna(row.get("capacity_mcm")) else None,
            "surface_area_km2": row.get("area_km2") if pd.notna(row.get("area_km2")) else None,
            "year_built": int(row["year_completed"]) if pd.notna(row.get("year_completed")) else None,
            "river": str(row.get("river", "")).strip() if pd.notna(row.get("river")) else None,
            "basin": str(row.get("major_basin", "")).strip() if pd.notna(row.get("major_basin")) else None,
            "purpose": row.get("purpose", []),
            "nearest_city": str(row.get("nearest_city", "")).strip() if pd.notna(row.get("nearest_city")) else None,
            "source": "fao",
        })

    log.info(f"FAO: parsed {len(records)} Morocco dams")
    return pd.DataFrame(records)


def parse_grand(geodar_dir):
    if geodar_dir is None:
        return None

    csv_path = None
    for f in Path(geodar_dir).rglob("GRanD_v13_issues.csv"):
        csv_path = f
        break

    if csv_path is None:
        log.warning("GRanD issues CSV not found in GeoDAR package")
        return None

    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    morocco = df[df["COUNTRY"] == "Morocco"].copy()
    log.info(f"GRanD: {len(morocco)} Morocco dams from issues file")

    use_cols = ["USE_IRRI", "USE_ELEC", "USE_SUPP", "USE_FCON", "USE_RECR",
                "USE_NAVI", "USE_FISH", "USE_PCON", "USE_LIVE", "USE_OTHR"]
    use_labels = ["irrigation", "hydropower", "water_supply", "flood_control", "recreation",
                  "navigation", "fishery", "pollution_control", "livestock", "other"]

    records = []
    for _, row in morocco.iterrows():
        lat = row.get("Lat_corrected") if pd.notna(row.get("Lat_corrected")) else row.get("LAT_DD")
        lon = row.get("Lon_corrected") if pd.notna(row.get("Lon_corrected")) else row.get("LONG_DD")

        purpose = []
        for uc, label in zip(use_cols, use_labels):
            val = str(row.get(uc, "")).strip().lower()
            if val and val not in ("nan", "", "-99", "0"):
                purpose.append(label)
        main_use = str(row.get("MAIN_USE", "")).strip()
        if main_use and main_use.lower() not in ("nan", ""):
            purpose.insert(0, main_use.lower())
            purpose = list(dict.fromkeys(purpose))

        cap = row.get("CAP_MCM")
        cap = float(cap) if pd.notna(cap) and float(cap) > 0 else None

        height = row.get("DAM_HGT_M")
        height = float(height) if pd.notna(height) and float(height) > 0 else None

        area = row.get("AREA_SKM")
        area = float(area) if pd.notna(area) and float(area) > 0 else None

        year = row.get("YEAR")
        year = int(year) if pd.notna(year) and int(year) > 1000 else None

        records.append({
            "grand_id": int(row["GRAND_ID"]),
            "name": str(row.get("DAM_NAME_c", "")).strip(),
            "reservoir_name": str(row.get("RES_NAME_c", "")).strip() if pd.notna(row.get("RES_NAME_c")) else None,
            "lat": float(lat) if pd.notna(lat) else None,
            "lon": float(lon) if pd.notna(lon) else None,
            "height_m": height,
            "capacity_mcm": cap,
            "surface_area_km2": area,
            "year_built": year,
            "river": str(row.get("RIVER_c", "")).strip() if pd.notna(row.get("RIVER_c")) else None,
            "basin": str(row.get("MAIN_BASIN", "")).strip() if pd.notna(row.get("MAIN_BASIN")) else None,
            "elevation_db_m": float(row["ELEV_MASL"]) if pd.notna(row.get("ELEV_MASL")) and float(row.get("ELEV_MASL", -99)) > 0 else None,
            "depth_m": float(row["DEPTH_M"]) if pd.notna(row.get("DEPTH_M")) and float(row.get("DEPTH_M", -99)) > 0 else None,
            "catchment_km2": float(row["CATCH_SKM"]) if pd.notna(row.get("CATCH_SKM")) and float(row.get("CATCH_SKM", -99)) > 0 else None,
            "purpose": purpose,
            "source": "grand",
        })

    log.info(f"GRanD: parsed {len(records)} Morocco dams with coordinates")
    return pd.DataFrame(records)


def parse_geodar(geodar_dir):
    if geodar_dir is None:
        return None

    csv_path = None
    for f in Path(geodar_dir).rglob("GeoDAR_v11_dams.csv"):
        csv_path = f
        break

    if csv_path is None:
        log.warning("GeoDAR v11 CSV not found")
        return None

    df = pd.read_csv(csv_path)
    lat_min, lat_max, lon_min, lon_max = get_bbox()
    morocco = df[
        (df["lat"] >= lat_min) & (df["lat"] <= lat_max) &
        (df["lon"] >= lon_min) & (df["lon"] <= lon_max)
    ].copy()

    records = []
    for _, row in morocco.iterrows():
        grand_id = int(row["id_grd_v13"]) if row["id_grd_v13"] != -999 else None
        vol = float(row["rv_mcm_v11"]) if row.get("rv_mcm_v11", -999) > 0 else None

        records.append({
            "geodar_id": int(row["id_v11"]),
            "grand_id": grand_id,
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "capacity_mcm": vol,
            "qa_rank": str(row.get("qa_rank", "")),
            "source": "geodar",
        })

    log.info(f"GeoDAR: {len(records)} Morocco dams")
    return pd.DataFrame(records)


def parse_hydrolakes(hydrolakes_dir):
    if hydrolakes_dir is None:
        return None

    shp = None
    for f in Path(hydrolakes_dir).rglob("*.shp"):
        shp = f
        break

    if shp is None:
        log.error("No HydroLAKES shapefile found")
        return None

    lat_min, lat_max, lon_min, lon_max = get_bbox()
    gdf = gpd.read_file(shp, bbox=(lon_min, lat_min, lon_max, lat_max))
    reservoirs = gdf[gdf["Lake_type"].isin([1, 2, 3])].copy()
    log.info(f"HydroLAKES: {len(reservoirs)} Morocco reservoirs")

    records = []
    for _, row in reservoirs.iterrows():
        centroid = row.geometry.centroid if row.geometry else None
        grand_id = int(row["Grand_id"]) if pd.notna(row.get("Grand_id")) and int(row["Grand_id"]) > 0 else None

        records.append({
            "hylak_id": int(row["Hylak_id"]),
            "grand_id": grand_id,
            "name": str(row.get("Lake_name", "")).strip() if pd.notna(row.get("Lake_name")) else None,
            "lat": centroid.y if centroid else None,
            "lon": centroid.x if centroid else None,
            "capacity_mcm": float(row["Vol_total"]) if pd.notna(row.get("Vol_total")) else None,
            "surface_area_km2": float(row["Lake_area"]) if pd.notna(row.get("Lake_area")) else None,
            "elevation_db_m": float(row["Elevation"]) if pd.notna(row.get("Elevation")) else None,
            "shore_len_km": float(row["Shore_len"]) if pd.notna(row.get("Shore_len")) else None,
            "depth_avg_m": float(row["Depth_avg"]) if pd.notna(row.get("Depth_avg")) else None,
            "source": "hydrolakes",
        })

    log.info(f"HydroLAKES: parsed {len(records)} Morocco reservoirs")
    return pd.DataFrame(records)


def download_all():
    results = {}
    log.info("Starting Morocco database downloads...")

    fao_path = download_fao()
    if fao_path:
        results["fao"] = parse_fao(fao_path)
        if results["fao"] is not None:
            log.info(f"FAO: {len(results['fao'])} Morocco dams")

    geodar_dir = download_geodar()
    if geodar_dir:
        results["grand"] = parse_grand(geodar_dir)
        results["geodar"] = parse_geodar(geodar_dir)

    hydrolakes_dir = download_hydrolakes()
    if hydrolakes_dir:
        results["hydrolakes"] = parse_hydrolakes(hydrolakes_dir)

    available = {k: v for k, v in results.items() if v is not None and len(v) > 0}
    if not available:
        log.error("No data sources loaded. Check network and data/raw/ directory.")
    else:
        log.info(f"Loaded sources: {list(available.keys())}")

    return available


def merge_registries(source_dfs):
    from ..merge import _normalize, _names_match, _coord_missing
    from ...geo import haversine_m

    fao = source_dfs.get("fao")
    grand = source_dfs.get("grand")
    geodar = source_dfs.get("geodar")
    hydrolakes = source_dfs.get("hydrolakes")

    if fao is None or len(fao) == 0:
        log.error("FAO data required as backbone for Morocco merge")
        return pd.DataFrame()

    grand_lookup = {}
    if grand is not None:
        for _, row in grand.iterrows():
            grand_lookup[row["grand_id"]] = row.to_dict()

    geodar_by_grand = {}
    geodar_no_grand = []
    if geodar is not None:
        for _, row in geodar.iterrows():
            if row.get("grand_id"):
                geodar_by_grand[row["grand_id"]] = row.to_dict()
            else:
                geodar_no_grand.append(row.to_dict())

    hl_by_grand = {}
    hl_no_grand = []
    if hydrolakes is not None:
        for _, row in hydrolakes.iterrows():
            if row.get("grand_id"):
                hl_by_grand[row["grand_id"]] = row.to_dict()
            else:
                hl_no_grand.append(row.to_dict())

    dams = []
    used_grand_ids = set()
    used_hl_indices = set()

    for _, fao_row in fao.iterrows():
        dam = _new_dam(fao_row)

        grand_match = _match_fao_to_grand(fao_row, grand_lookup, used_grand_ids)
        if grand_match:
            gid = grand_match["grand_id"]
            dam["grand_id"] = gid
            used_grand_ids.add(gid)
            _enrich_from_grand(dam, grand_match)

            if gid in geodar_by_grand:
                _enrich_coords_from_geodar(dam, geodar_by_grand[gid])

            if gid in hl_by_grand:
                _enrich_from_hydrolakes(dam, hl_by_grand[gid])

        if _coord_missing(dam):
            known = KNOWN_COORDINATES.get(dam["name"])
            if known:
                dam["lat"], dam["lon"] = known
                log.info(f"Applied known coordinates for {dam['name']}")
            else:
                _try_coord_from_proximity(dam, hl_no_grand, used_hl_indices)

        dams.append(dam)

    for gid, grand_row in grand_lookup.items():
        if gid in used_grand_ids:
            continue
        dam = _new_dam_from_grand(grand_row)
        dam["grand_id"] = gid

        if gid in geodar_by_grand:
            _enrich_coords_from_geodar(dam, geodar_by_grand[gid])
        if gid in hl_by_grand:
            _enrich_from_hydrolakes(dam, hl_by_grand[gid])

        if not _is_duplicate(dam, dams):
            dams.append(dam)
            used_grand_ids.add(gid)

    for hl_row in hl_no_grand:
        idx = id(hl_row)
        if idx in used_hl_indices:
            continue
        if hl_row.get("lat") is None:
            continue
        if not _is_near_any(hl_row, dams):
            dam = _new_dam_from_hydrolakes(hl_row)
            dams.append(dam)

    dams.sort(key=lambda d: d.get("name", ""))
    for i, dam in enumerate(dams):
        dam["id"] = f"MAR-{i + 1:03d}"

    with_coords = sum(1 for d in dams if d.get("lat") is not None)
    with_height = sum(1 for d in dams if d.get("height_m") is not None)
    with_cap = sum(1 for d in dams if d.get("capacity_mcm") is not None)
    log.info(f"Merged registry: {len(dams)} dams")
    log.info(f"  With coords: {with_coords}/{len(dams)}")
    log.info(f"  With height: {with_height}/{len(dams)}")
    log.info(f"  With capacity: {with_cap}/{len(dams)}")

    return pd.DataFrame(dams)


PROXIMITY_THRESHOLD_M = 2000


def _match_fao_to_grand(fao_row, grand_lookup, used_grand_ids):
    from ..merge import _names_match
    from ...geo import haversine_m

    fao_name = fao_row.get("name", "")
    fao_alt = fao_row.get("alt_name", "")
    alias = FAO_TO_GRAND_ALIASES.get(fao_name)

    for gid, grand_row in grand_lookup.items():
        if gid in used_grand_ids:
            continue
        grand_name = grand_row.get("name", "")
        grand_res = grand_row.get("reservoir_name", "")

        if _names_match(fao_name, grand_name):
            return grand_row
        if alias and _names_match(alias, grand_name):
            return grand_row
        if fao_alt and isinstance(fao_alt, str) and _names_match(fao_alt, grand_name):
            return grand_row
        if grand_res and isinstance(grand_res, str) and _names_match(fao_name, grand_res):
            return grand_row

    fao_lat = fao_row.get("lat")
    fao_lon = fao_row.get("lon")
    if fao_lat is not None and fao_lon is not None:
        try:
            import math
            if math.isnan(float(fao_lat)):
                return None
        except (ValueError, TypeError):
            return None
        for gid, grand_row in grand_lookup.items():
            if gid in used_grand_ids:
                continue
            if grand_row.get("lat") is None:
                continue
            dist = haversine_m(fao_lat, fao_lon, grand_row["lat"], grand_row["lon"])
            if dist < PROXIMITY_THRESHOLD_M:
                return grand_row

    return None


def _new_dam(fao_row):
    return {
        "name": fao_row.get("name"),
        "alt_names": [fao_row["alt_name"]] if fao_row.get("alt_name") else [],
        "lat": fao_row.get("lat"),
        "lon": fao_row.get("lon"),
        "height_m": fao_row.get("height_m"),
        "capacity_mcm": fao_row.get("capacity_mcm"),
        "surface_area_km2": fao_row.get("surface_area_km2"),
        "year_built": fao_row.get("year_built"),
        "river": fao_row.get("river"),
        "basin": fao_row.get("basin"),
        "purpose": fao_row.get("purpose", []),
        "nearest_city": fao_row.get("nearest_city"),
        "sources": ["fao"],
        "grand_id": None,
        "status": "operational",
    }


def _new_dam_from_grand(grand_row):
    return {
        "name": grand_row.get("name"),
        "alt_names": [grand_row["reservoir_name"]] if grand_row.get("reservoir_name") else [],
        "lat": grand_row.get("lat"),
        "lon": grand_row.get("lon"),
        "height_m": grand_row.get("height_m"),
        "capacity_mcm": grand_row.get("capacity_mcm"),
        "surface_area_km2": grand_row.get("surface_area_km2"),
        "year_built": grand_row.get("year_built"),
        "river": grand_row.get("river"),
        "basin": grand_row.get("basin"),
        "purpose": grand_row.get("purpose", []),
        "nearest_city": None,
        "elevation_db_m": grand_row.get("elevation_db_m"),
        "depth_m": grand_row.get("depth_m"),
        "catchment_km2": grand_row.get("catchment_km2"),
        "sources": ["grand"],
        "grand_id": grand_row.get("grand_id"),
        "status": "operational",
    }


def _new_dam_from_hydrolakes(hl_row):
    name = hl_row.get("name")
    if not name or name.lower() in ("nan", "none", ""):
        name = f"Unnamed reservoir (HydroLAKES {hl_row.get('hylak_id', '')})"

    return {
        "name": name,
        "alt_names": [],
        "lat": hl_row.get("lat"),
        "lon": hl_row.get("lon"),
        "height_m": None,
        "capacity_mcm": hl_row.get("capacity_mcm"),
        "surface_area_km2": hl_row.get("surface_area_km2"),
        "year_built": None,
        "river": None,
        "basin": None,
        "purpose": [],
        "nearest_city": None,
        "elevation_db_m": hl_row.get("elevation_db_m"),
        "shore_len_km": hl_row.get("shore_len_km"),
        "depth_avg_m": hl_row.get("depth_avg_m"),
        "sources": ["hydrolakes"],
        "grand_id": None,
        "status": "operational",
    }


def _enrich_from_grand(dam, grand_row):
    from ..merge import _coord_missing

    if "grand" not in dam["sources"]:
        dam["sources"].append("grand")

    grand_name = grand_row.get("name", "")
    if grand_name and grand_name != dam["name"]:
        if grand_name not in dam.get("alt_names", []):
            dam.setdefault("alt_names", []).append(grand_name)

    if _coord_missing(dam) and grand_row.get("lat") is not None:
        dam["lat"] = grand_row["lat"]
        dam["lon"] = grand_row["lon"]

    if dam["height_m"] is None and grand_row.get("height_m") is not None:
        dam["height_m"] = grand_row["height_m"]
    if dam["capacity_mcm"] is None and grand_row.get("capacity_mcm") is not None:
        dam["capacity_mcm"] = grand_row["capacity_mcm"]
    if dam["surface_area_km2"] is None and grand_row.get("surface_area_km2") is not None:
        dam["surface_area_km2"] = grand_row["surface_area_km2"]
    if dam["year_built"] is None and grand_row.get("year_built") is not None:
        dam["year_built"] = grand_row["year_built"]

    for field in ["elevation_db_m", "depth_m", "catchment_km2"]:
        if grand_row.get(field) is not None:
            dam[field] = grand_row[field]


def _enrich_coords_from_geodar(dam, geodar_row):
    from ..merge import _coord_missing

    if "geodar" not in dam.get("sources", []):
        dam.setdefault("sources", []).append("geodar")

    if geodar_row.get("qa_rank", "").startswith(("A", "B")):
        dam["lat"] = geodar_row["lat"]
        dam["lon"] = geodar_row["lon"]
    elif _coord_missing(dam):
        dam["lat"] = geodar_row["lat"]
        dam["lon"] = geodar_row["lon"]


def _enrich_from_hydrolakes(dam, hl_row):
    if "hydrolakes" not in dam.get("sources", []):
        dam.setdefault("sources", []).append("hydrolakes")

    if dam.get("surface_area_km2") is None and hl_row.get("surface_area_km2") is not None:
        dam["surface_area_km2"] = hl_row["surface_area_km2"]
    if hl_row.get("elevation_db_m") is not None:
        dam["elevation_db_m"] = hl_row["elevation_db_m"]
    if hl_row.get("shore_len_km") is not None:
        dam["shore_len_km"] = hl_row["shore_len_km"]
    if hl_row.get("depth_avg_m") is not None:
        dam["depth_avg_m"] = hl_row["depth_avg_m"]


def _try_coord_from_proximity(dam, hl_list, used_indices):
    if dam["lat"] is not None:
        return
    cap = dam.get("capacity_mcm")
    if cap is None:
        return

    for hl_row in hl_list:
        if id(hl_row) in used_indices:
            continue
        hl_cap = hl_row.get("capacity_mcm")
        if hl_cap is None:
            continue
        ratio = min(cap, hl_cap) / max(cap, hl_cap) if max(cap, hl_cap) > 0 else 0
        if ratio > 0.5:
            dam["lat"] = hl_row["lat"]
            dam["lon"] = hl_row["lon"]
            dam["elevation_db_m"] = hl_row.get("elevation_db_m")
            dam["surface_area_km2"] = dam.get("surface_area_km2") or hl_row.get("surface_area_km2")
            dam["shore_len_km"] = hl_row.get("shore_len_km")
            dam["depth_avg_m"] = hl_row.get("depth_avg_m")
            if "hydrolakes" not in dam.get("sources", []):
                dam.setdefault("sources", []).append("hydrolakes")
            used_indices.add(id(hl_row))
            log.info(f"Matched {dam['name']} to HydroLAKES by capacity ({cap} vs {hl_cap} MCM)")
            return


def _is_duplicate(dam, existing_dams):
    from ..merge import _coord_missing
    from ...geo import haversine_m

    if _coord_missing(dam):
        return False
    for existing in existing_dams:
        if _coord_missing(existing):
            continue
        dist = haversine_m(dam["lat"], dam["lon"], existing["lat"], existing["lon"])
        if dist < PROXIMITY_THRESHOLD_M:
            return True
    return False


def _is_near_any(row, existing_dams):
    from ..merge import _coord_missing
    from ...geo import haversine_m

    if row.get("lat") is None:
        return False
    for existing in existing_dams:
        if _coord_missing(existing):
            continue
        dist = haversine_m(row["lat"], row["lon"], existing["lat"], existing["lon"])
        if dist < PROXIMITY_THRESHOLD_M:
            return True
    return False
