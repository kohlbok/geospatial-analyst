import logging

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import LineString

from ..config import load_config, DATA_RAW, get_bbox

log = logging.getLogger(__name__)


def apply_tier1_filters(pairs_df, params=None):
    if params is None:
        cfg = load_config()
        params = cfg.get("filters", {})

    min_head = params.get("min_head_m", 100)
    max_ratio = params.get("max_distance_head_ratio", params.get("max_distance_km", 30) * 1000 / params.get("min_head_m", 100))
    min_capacity = params.get("min_capacity_mcm", 1)
    max_distance = params.get("max_distance_km", 30)

    log.info(f"Tier 1 filters: min_head={min_head}m, max_ratio={max_ratio}, max_dist={max_distance}km, min_capacity={min_capacity} MCM")
    log.info(f"Input pairs: {len(pairs_df)}")

    results = []
    for _, pair in pairs_df.iterrows():
        status = "pass"
        reasons = []

        if pair["head_m"] < min_head:
            status = "fail"
            reasons.append(f"head {pair['head_m']}m < {min_head}m minimum")

        if pair["distance_km"] > max_distance:
            status = "fail"
            reasons.append(f"distance {pair['distance_km']}km > {max_distance}km maximum")

        if pair["distance_head_ratio"] > max_ratio:
            status = "fail"
            reasons.append(
                f"distance/head ratio {pair['distance_head_ratio']} > {max_ratio} maximum"
            )

        upper_cap = pair.get("upper_capacity_mcm")
        lower_cap = pair.get("lower_capacity_mcm")

        if upper_cap is not None and upper_cap < min_capacity:
            status = "fail"
            reasons.append(f"upper reservoir {upper_cap} MCM < {min_capacity} MCM minimum")
        if lower_cap is not None and lower_cap < min_capacity:
            status = "fail"
            reasons.append(f"lower reservoir {lower_cap} MCM < {min_capacity} MCM minimum")

        if status == "pass":
            head_margin = (pair["head_m"] - min_head) / min_head
            ratio_margin = (max_ratio - pair["distance_head_ratio"]) / max_ratio
            if head_margin < 0.1 or ratio_margin < 0.1:
                status = "borderline"
                reasons.append("near threshold boundaries")

        row = pair.to_dict()
        row["tier1_status"] = status
        row["tier1_reasons"] = "; ".join(reasons) if reasons else "all criteria met"
        results.append(row)

    result_df = pd.DataFrame(results)
    passed = result_df[result_df["tier1_status"].isin(["pass", "borderline"])]
    failed = result_df[result_df["tier1_status"] == "fail"]
    borderline = result_df[result_df["tier1_status"] == "borderline"]

    log.info(
        f"Tier 1 results: {len(passed)} pass ({len(borderline)} borderline), "
        f"{len(failed)} fail"
    )
    return result_df


def apply_tier2_filters(pairs_df, dam_registry=None):
    config = load_config()
    params = config.get("screening", {})
    buffer_km = params.get("protected_area_buffer_km", 1)

    log.info(f"Tier 2 filters on {len(pairs_df)} pairs")

    passed = pairs_df[pairs_df["tier1_status"].isin(["pass", "borderline"])].copy()
    failed = pairs_df[pairs_df["tier1_status"] == "fail"].copy()

    protected_areas = _load_protected_areas()

    results = []
    for _, pair in passed.iterrows():
        row = pair.to_dict()
        status = pair.get("tier1_status", "pass")
        reasons = []

        if protected_areas is not None:
            line = LineString([
                (pair["upper_lon"], pair["upper_lat"]),
                (pair["lower_lon"], pair["lower_lat"]),
            ])
            buffered = line.buffer(buffer_km / 111.0)
            intersects = protected_areas.intersects(buffered).any()
            if intersects:
                status = "fail"
                reasons.append("route intersects protected area")

        row["tier2_status"] = status
        row["tier2_reasons"] = "; ".join(reasons) if reasons else "passed tier 2"
        results.append(row)

    for _, pair in failed.iterrows():
        row = pair.to_dict()
        row["tier2_status"] = "fail"
        row["tier2_reasons"] = "failed tier 1"
        results.append(row)

    result_df = pd.DataFrame(results)
    viable = result_df[result_df["tier2_status"].isin(["pass", "borderline"])]
    log.info(f"Tier 2 results: {len(viable)} viable pairs")
    return result_df


def _load_protected_areas():
    wdpa_dir = DATA_RAW / "wdpa"
    if wdpa_dir.exists():
        shp_files = list(wdpa_dir.rglob("*.shp"))
        if shp_files:
            try:
                lat_min, lat_max, lon_min, lon_max = get_bbox()
                gdf = gpd.read_file(shp_files[0], bbox=(lon_min, lat_min, lon_max, lat_max))
                log.info(f"Loaded {len(gdf)} protected areas from WDPA")
                return gdf
            except Exception as e:
                log.warning(f"Failed to read WDPA shapefile: {e}")

    log.info("WDPA data not available locally, attempting OSM lookup")
    try:
        return _fetch_protected_areas_osm()
    except Exception as e:
        log.warning(f"Could not load protected areas: {e}")
        return None


def _fetch_protected_areas_osm():
    lat_min, lat_max, lon_min, lon_max = get_bbox()

    query = f"""
    [out:json][timeout:120];
    (
      way["boundary"="protected_area"]({lat_min},{lon_min},{lat_max},{lon_max});
      relation["boundary"="protected_area"]({lat_min},{lon_min},{lat_max},{lon_max});
      way["boundary"="national_park"]({lat_min},{lon_min},{lat_max},{lon_max});
      relation["boundary"="national_park"]({lat_min},{lon_min},{lat_max},{lon_max});
    );
    out geom;
    """
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("elements"):
            log.info("No protected areas found via OSM")
            return None

        from shapely.geometry import Polygon
        geometries = []
        for element in data["elements"]:
            if "geometry" in element:
                coords = [(n["lon"], n["lat"]) for n in element["geometry"]]
                if len(coords) >= 3:
                    try:
                        geometries.append(Polygon(coords))
                    except Exception:
                        pass

        if geometries:
            gdf = gpd.GeoDataFrame(geometry=geometries, crs="EPSG:4326")
            log.info(f"Loaded {len(gdf)} protected areas from OSM")
            return gdf
    except Exception as e:
        log.warning(f"OSM protected areas query failed: {e}")

    return None
