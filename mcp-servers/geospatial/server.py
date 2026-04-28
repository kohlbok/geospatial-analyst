import logging
import sys
from pathlib import Path

import orjson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

from geospatial.config import (
    load_config, reload_config, load_dams, save_dams,
    list_data_files, set_active_file, get_active_file,
    safe_dumps, DATA_PROCESSED, OUTPUT_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("psh-screening")

mcp = FastMCP("PSH Screening")


_pairs_cache: dict = {"all_pairs": None, "filtered_pairs": None, "scored_pairs": None}


def _cache_get(key, path):
    df = _pairs_cache.get(key)
    if df is not None:
        return df
    if path.exists():
        import pandas as pd
        df = pd.read_json(path)
        _pairs_cache[key] = df
        return df
    return None


def _cache_set(key, df):
    _pairs_cache[key] = df


def _cache_clear():
    for k in _pairs_cache:
        _pairs_cache[k] = None


def _pid_alive(pid):
    import os
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@mcp.tool()
def cleanup(targets: str = "screen") -> str:
    """Remove generated outputs and intermediates for a fresh run.
    targets: "screen" clears output/ and intermediate/. "siting" clears siting outputs and intermediates only. "all" does both. Never touches data/.cache/srtm or data/.cache/raw."""
    import shutil
    from geospatial.config import OUTPUT_DIR, DATA_PROCESSED

    removed = []
    errors = []

    def _rm(path):
        try:
            if path.is_dir():
                shutil.rmtree(path)
                removed.append(f"dir: {path}")
            elif path.exists():
                path.unlink()
                removed.append(f"file: {path}")
        except Exception as e:
            errors.append(f"{path}: {e}")

    target = targets.lower().strip()

    if target in ("screen", "all"):
        if OUTPUT_DIR.exists():
            for child in OUTPUT_DIR.iterdir():
                _rm(child)
        if DATA_PROCESSED.exists():
            for child in DATA_PROCESSED.iterdir():
                _rm(child)

    if target in ("siting", "all"):
        siting_outputs = [
            OUTPUT_DIR / "siting_map.html",
            OUTPUT_DIR / "siting_results.xlsx",
            OUTPUT_DIR / "siting_profiles.pdf",
            OUTPUT_DIR / "siting_tier1.xlsx",
        ]
        siting_intermediates = [
            DATA_PROCESSED / "siting_tier1.json",
            DATA_PROCESSED / "siting_candidates.json",
            DATA_PROCESSED / "siting_candidates_partial.json",
            DATA_PROCESSED / "siting_scan_kills.json",
            DATA_PROCESSED / "siting_scan.log",
            DATA_PROCESSED / "siting_scan.pid",
        ]
        for path in siting_outputs + siting_intermediates:
            if path.exists():
                _rm(path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    _cache_clear()

    return safe_dumps({
        "status": "ok",
        "target": target,
        "removed_count": len(removed),
        "errors": errors,
    })


@mcp.tool()
def load_dam_registry(file: str = "") -> str:
    """Load a dam registry from the data/ directory. Pass a filename to select it, or omit to list available files."""
    if not file:
        files = list_data_files()
        if not files:
            return safe_dumps({"error": "No data files found in data/. Place a .json, .xlsx, or .csv file there."})
        active = get_active_file()
        return safe_dumps({"available_files": files, "active": active.name if active else None})

    result = set_active_file(file)
    if result is None:
        return safe_dumps({"error": f"File '{file}' not found in data/"})
    _cache_clear()
    if result == "needs_parsing":
        return safe_dumps({
            "status": "needs_parsing",
            "file": file,
            "message": f"'{file}' needs to be converted to JSON first. Use inspect_file to see its columns, then parse_tabular to convert it with the right column mapping. The output JSON should be saved as '{Path(file).stem}.json' in data/.",
        })

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": f"Could not parse '{file}'."})

    total = len(dams)
    coverage = {
        "coordinates": sum(1 for d in dams if d.get("lat") is not None),
        "elevation": sum(1 for d in dams if d.get("elevation_wall_m") is not None or d.get("elevation_m") is not None),
        "height": sum(1 for d in dams if d.get("height_m") is not None),
        "capacity": sum(1 for d in dams if d.get("capacity_mcm") is not None and d.get("capacity_mcm", 0) > 0),
        "grid_distance": sum(1 for d in dams if d.get("grid_distance_km") is not None),
    }

    return safe_dumps({
        "status": "ok",
        "total_dams": total,
        "coverage": coverage,
        "sample": dams[:3],
    })


@mcp.tool()
def generate_pairs() -> str:
    """Generate all possible dam pair combinations with head and distance calculations."""
    import pandas as pd
    from geospatial.screening.pairs import generate_pairs as do_generate

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    registry = pd.DataFrame(dams)
    if "elevation_wall_m" not in registry.columns or registry["elevation_wall_m"].isna().all():
        registry["elevation_wall_m"] = registry.get("elevation_m")

    pairs = do_generate(registry)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    pairs.to_json(DATA_PROCESSED / "all_pairs.json", orient="records", default_handler=str)
    _cache_set("all_pairs", pairs)

    return safe_dumps({
        "status": "ok",
        "total_pairs": len(pairs),
        "head_range": f"{pairs['head_m'].min():.0f}-{pairs['head_m'].max():.0f}m" if len(pairs) > 0 else "N/A",
        "distance_range": f"{pairs['distance_km'].min():.1f}-{pairs['distance_km'].max():.1f}km" if len(pairs) > 0 else "N/A",
    })


@mcp.tool()
def screen_pairs() -> str:
    """Apply screening filters and score all pairs. Returns ranked list."""
    from geospatial.screening.filters import apply_tier1_filters, apply_energy_filters
    from geospatial.scoring.energy import calculate_all_energies
    from geospatial.scoring.cost import calculate_all_costs
    from geospatial.scoring.composite import score_pairs as do_score

    pairs = _cache_get("all_pairs", DATA_PROCESSED / "all_pairs.json")
    if pairs is None:
        return safe_dumps({"error": "Run generate_pairs first"})

    config = load_config()

    filtered = apply_tier1_filters(pairs)
    viable = filtered[filtered["tier1_status"] == "pass"].copy()

    if len(viable) == 0:
        return safe_dumps({"status": "ok", "viable_pairs": 0, "message": "No pairs passed filters"})

    with_energy = calculate_all_energies(viable)
    energy_filtered = apply_energy_filters(with_energy)
    viable_energy = energy_filtered[energy_filtered["energy_filter_status"] == "pass"].copy()

    if len(viable_energy) == 0:
        return safe_dumps({"status": "ok", "viable_pairs": 0, "message": "No pairs passed energy/power filters"})

    with_costs = calculate_all_costs(viable_energy)
    scored = do_score(with_costs)

    scored.to_json(DATA_PROCESSED / "scored_pairs.json", orient="records", default_handler=str)
    filtered.to_json(DATA_PROCESSED / "filtered_pairs.json", orient="records", default_handler=str)
    _cache_set("scored_pairs", scored)
    _cache_set("filtered_pairs", filtered)

    top = scored.head(10)
    top_list = []
    for _, row in top.iterrows():
        top_list.append(row.to_dict())

    return safe_dumps({
        "status": "ok",
        "total_evaluated": len(pairs),
        "tier1_viable": len(viable),
        "energy_viable": len(viable_energy),
        "scored_pairs": len(scored),
        "top_10": top_list,
    })


@mcp.tool()
def generate_map() -> str:
    """Generate a single interactive HTML map showing all dams and top pairs."""
    import pandas as pd
    from geospatial.visualization.maps import generate_combined_map

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    scored = _cache_get("scored_pairs", DATA_PROCESSED / "scored_pairs.json")
    all_pairs = _cache_get("all_pairs", DATA_PROCESSED / "all_pairs.json")
    filtered = _cache_get("filtered_pairs", DATA_PROCESSED / "filtered_pairs.json")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    map_path = generate_combined_map(pd.DataFrame(dams), scored, all_pairs, filtered)
    return safe_dumps({"status": "ok", "map": str(map_path)})


@mcp.tool()
def generate_overview_map() -> str:
    """Generate an interactive overview map of all dams color-coded by status. Used during data collection for visual review. Saves to data/overview.html."""
    import pandas as pd
    from geospatial.visualization.maps import generate_overview_map as do_generate

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    map_path = do_generate(pd.DataFrame(dams))
    return safe_dumps({"status": "ok", "map": str(map_path)})


@mcp.tool()
def generate_results() -> str:
    """Generate final output files: results.xlsx, results.json, pairs.kml, pairs.geojson."""
    import pandas as pd
    from geospatial.visualization.export import generate_clean_outputs

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    scored = _cache_get("scored_pairs", DATA_PROCESSED / "scored_pairs.json")
    if scored is None:
        return safe_dumps({"error": "Run screen_pairs first"})

    all_pairs = _cache_get("all_pairs", DATA_PROCESSED / "all_pairs.json")
    filtered = _cache_get("filtered_pairs", DATA_PROCESSED / "filtered_pairs.json")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = generate_clean_outputs(pd.DataFrame(dams), scored, all_pairs, filtered)
    return safe_dumps({"status": "ok", "outputs": paths})


@mcp.tool()
def generate_executive_summary(expert_review: str) -> str:
    """Generate a PDF executive summary report. expert_review is a JSON list of pair assessments, each with: rank, upper_dam, lower_dam, head_m, distance_km, energy_mwh, capex_per_mwh_usd, capex_advantage_pct, score, grid_distance_km, verdict, assessment."""
    from datetime import datetime

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    scored_path = DATA_PROCESSED / "scored_pairs.json"
    if not scored_path.exists():
        return safe_dumps({"error": "Run screen_pairs first"})

    import pandas as pd
    scored = pd.read_json(scored_path)
    config = load_config()

    pairs_data = orjson.loads(expert_review) if isinstance(expert_review, str) else expert_review

    report_data = {
        "country": config.get("country", "Unknown"),
        "date": datetime.now().strftime("%B %d, %Y"),
        "total_dams": len(dams),
        "total_pairs": len(dams) * (len(dams) - 1) // 2,
        "viable_pairs": len(scored),
        "summary_text": (
            f"This report presents the results of a systematic pumped storage hydropower screening "
            f"across {len(dams)} dams. {len(scored)} dam pairs passed the engineering filters "
            f"(minimum {config['filters']['min_head_m']}m head, maximum {config['filters']['max_distance_km']}km distance, "
            f"minimum {config['filters']['min_capacity_mcm']} MCM capacity) and were scored on energy potential (40%), "
            f"cost competitiveness vs battery storage CAPEX (35%), and grid proximity (25%)."
        ),
        "min_head_m": config["filters"]["min_head_m"],
        "max_distance_km": config["filters"]["max_distance_km"],
        "min_capacity_mcm": config["filters"]["min_capacity_mcm"],
        "max_distance_head_ratio": config["filters"].get("max_distance_head_ratio", 50),
        "battery_capex": config["cost_benchmarks"].get("battery_capex_usd_per_mwh", 100_000),
        "battery_cost": config["cost_benchmarks"]["battery_usd_per_mwh"],
        "efficiency": int(config["physics"]["round_trip_efficiency"] * 100),
        "usable_volume_pct": int(config["physics"].get("usable_volume_fraction", 0.6) * 100),
        "power_duration_hours": config["physics"].get("power_duration_hours", 8),
        "penstock_per_km": config["cost_model"]["penstock_usd_per_km"],
        "upper_res_per_mcm": config["cost_model"]["reservoir_upper_usd_per_mcm"],
        "lower_res_per_mcm": config["cost_model"]["reservoir_lower_usd_per_mcm"],
        "powerhouse_per_mw": config["cost_model"]["powerhouse_usd_per_mw"],
        "fixed_costs": config["cost_model"].get("roads_usd_fixed", 0),
        "grid_per_km": config["cost_model"].get("grid_connection_usd_per_km", 0),
        "weights": config["scoring_weights"],
        "pairs": pairs_data,
    }

    data_path = OUTPUT_DIR / "report_data.json"
    with open(data_path, "w", encoding="utf-8") as f:
        f.write(safe_dumps(report_data, indent=2))

    pdf_path = OUTPUT_DIR / "executive-summary.pdf"
    try:
        from jinja2 import Template

        project_root = Path(__file__).resolve().parent.parent.parent
        template_path = project_root / "templates" / "executive-summary.html"

        with open(template_path, encoding="utf-8") as f:
            template = Template(f.read())

        rendered = template.render(**report_data)

        html_output = pdf_path.with_suffix(".html")
        html_output.write_text(rendered, encoding="utf-8")

        try:
            from weasyprint import HTML
            HTML(string=rendered, base_url=str(template_path.parent)).write_pdf(str(pdf_path))
            return safe_dumps({"status": "ok", "pdf": str(pdf_path), "html": str(html_output)})
        except ImportError:
            return safe_dumps({"status": "ok", "html": str(html_output), "pdf_skipped": "weasyprint not available -- open the HTML in a browser or print to PDF from there"})

    except Exception as e:
        return safe_dumps({"error": str(e)})


@mcp.tool()
def download_file(url: str, filename: str, subfolder: str = "") -> str:
    """Download any file from a URL to data/.cache/raw/{subfolder}/{filename}."""
    from geospatial.ingestion.download import _download_file, _download_and_extract_zip
    from geospatial.config import DATA_RAW

    dest_dir = DATA_RAW / subfolder if subfolder else DATA_RAW
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename

    if filename.endswith(".zip"):
        extract_dir = dest_dir / filename.replace(".zip", "")
        success = _download_and_extract_zip(url, extract_dir, filename)
        if success:
            files = [str(f.relative_to(extract_dir)) for f in extract_dir.rglob("*") if f.is_file()][:20]
            return safe_dumps({"status": "ok", "extracted_to": str(extract_dir), "files": files})
        return safe_dumps({"error": f"Failed to download {url}"})

    success = _download_file(url, dest, filename)
    if success:
        return safe_dumps({"status": "ok", "path": str(dest), "size_bytes": dest.stat().st_size})
    return safe_dumps({"error": f"Failed to download {url}"})


@mcp.tool()
def inspect_file(path: str, max_rows: int = 20) -> str:
    """Inspect any tabular file (CSV, Excel, Shapefile, GeoJSON). Returns columns, sample rows."""
    from geospatial.ingestion.inspect import inspect_file as do_inspect
    return safe_dumps(do_inspect(path, max_rows))


@mcp.tool()
def parse_tabular(path: str, column_mapping: str, filters: str = "[]", output_name: str = "parsed") -> str:
    """Parse a tabular file with agent-provided column mapping. column_mapping is JSON dict, filters is JSON list."""
    from geospatial.ingestion.parse import parse_tabular as do_parse
    mapping = orjson.loads(column_mapping) if isinstance(column_mapping, str) else column_mapping
    filt = orjson.loads(filters) if isinstance(filters, str) else filters
    return safe_dumps(do_parse(path, mapping, filt, output_name))


@mcp.tool()
def merge_sources(proximity_threshold_m: int = 0, output_name: str = "dams") -> str:
    """Merge all staged dam sources using coordinate proximity clustering. Saves merged result to data/{output_name}.json and sets it as the active file. Returns stats and edge cases."""
    from geospatial.config import DATA_DIR, _save_json
    from geospatial.ingestion.staging import load_all_staged
    from geospatial.ingestion.merge import merge_sources as do_merge

    staged = load_all_staged()
    if not staged:
        return safe_dumps({"error": "No staged sources found. Run parse_tabular first to stage data."})

    config = load_config()
    threshold = proximity_threshold_m or config.get("ingestion", {}).get("proximity_threshold_m", 500)

    result = do_merge(staged, threshold_m=threshold)

    out_path = DATA_DIR / f"{output_name}.json"
    _save_json(result["dams"], out_path)
    set_active_file(f"{output_name}.json")

    edge_case_summary = []
    for ec in result["edge_cases"][:20]:
        edge_case_summary.append({
            "name": ec.get("name", "Unknown"),
            "source": ec.get("_source", ""),
            "height_m": ec.get("height_m"),
            "capacity_mcm": ec.get("capacity_mcm"),
        })

    return safe_dumps({
        "status": "ok",
        "stats": result["stats"],
        "output_path": str(out_path),
        "edge_cases": edge_case_summary,
        "edge_case_count": len(result["edge_cases"]),
    })


@mcp.tool()
def enrich_names() -> str:
    """Look up canonical names for all dams from OpenStreetMap water features. Single batch query, matches by proximity."""
    from geospatial.ingestion.osm import enrich_dams_with_names

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    enriched = enrich_dams_with_names(dams)
    save_dams(enriched)

    from_osm = sum(1 for d in enriched if d.get("name_source") == "osm")
    still_unknown = sum(1 for d in enriched if d.get("name") in (None, "", "Unknown"))

    return safe_dumps({
        "status": "ok",
        "total_dams": len(enriched),
        "named_from_osm": from_osm,
        "still_unnamed": still_unknown,
        "sample": [{"name": d["name"], "name_source": d.get("name_source"), "name_distance_km": d.get("name_distance_km")} for d in enriched[:5]],
    })


@mcp.tool()
def enrich_grid_distance(max_workers: int = 3) -> str:
    """Look up nearest power substation (OpenStreetMap) for each dam. Adds grid_distance_km to the active data file. Runs in parallel."""
    from geospatial.ingestion.osm import enrich_dams_with_grid

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    already = sum(1 for d in dams if d.get("grid_distance_km") is not None)
    if already == len(dams):
        return safe_dumps({"status": "ok", "message": "All dams already have grid distance", "total": len(dams)})

    enriched = enrich_dams_with_grid(dams, max_workers=max_workers)

    save_dams(enriched)

    with_grid = sum(1 for d in enriched if d.get("grid_distance_km") is not None)
    avg_dist = sum(d["grid_distance_km"] for d in enriched if d.get("grid_distance_km")) / max(with_grid, 1)

    return safe_dumps({
        "status": "ok",
        "total_dams": len(enriched),
        "with_grid_distance": with_grid,
        "average_grid_distance_km": round(avg_dist, 1),
        "sample": [{"name": d["name"], "grid_distance_km": d.get("grid_distance_km")} for d in enriched[:5]],
    })


@mcp.tool()
def enrich_elevation() -> str:
    """Add SRTM 30m elevation data to dams in the registry."""
    import pandas as pd
    from geospatial.ingestion.elevate import enrich_dam_elevations

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    registry = pd.DataFrame(dams)
    enriched = enrich_dam_elevations(registry)

    result_dams = enriched.to_dict("records")
    save_dams(result_dams)

    missing = enriched["elevation_wall_m"].isna().sum()
    return safe_dumps({
        "status": "ok",
        "total_dams": len(enriched),
        "elevation_coverage": f"{len(enriched) - missing}/{len(enriched)}",
    })


@mcp.tool()
def enrich_coordinates() -> str:
    """Geocode dams that have no coordinates using OSM name search, nearby city lookup, and Nominatim fallback."""
    from geospatial.ingestion.geocode import geocode_unlocated

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    enriched, found = geocode_unlocated(dams)
    save_dams(enriched)

    still_missing = sum(1 for d in enriched if d.get("lat") is None)
    return safe_dumps({
        "status": "ok",
        "total_dams": len(enriched),
        "geocoded": found,
        "still_missing_coords": still_missing,
    })


@mcp.tool()
def fetch_under_construction() -> str:
    """Fetch under-construction dams from WikiData and OpenStreetMap. Returns records that can be added to staged sources."""
    from geospatial.ingestion.under_construction import fetch_all_under_construction

    records = fetch_all_under_construction()
    if not records:
        return safe_dumps({"status": "ok", "count": 0, "message": "No under-construction dams found"})

    from geospatial.ingestion.staging import save_staged_source
    result = save_staged_source("under_construction", records)

    return safe_dumps({
        "status": "ok",
        "count": len(records),
        "staged": result,
        "sample": records[:3],
    })


@mcp.tool()
def tier1_elevation_screen() -> str:
    """Run Tier 1 elevation viability check on all dams. Excludes existing PSH dams. Saves siting_tier1.json."""
    from geospatial.terrain.dem import load_dem_patch
    from geospatial.siting.scanner import tier1_screen

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    config = reload_config()
    siting = config.get("siting", {})
    search_radius_km = siting.get("search_radius_km", 20)
    resolution_m = siting.get("tier1_resolution_m", 90)

    def _is_existing_psh(dam):
        status = str(dam.get("status") or "").lower()
        return "psh" in status or "step" in status

    with_coords = [d for d in dams if d.get("lat") is not None and d.get("lon") is not None]
    screened = [d for d in with_coords if not _is_existing_psh(d)]
    psh_excluded = len(with_coords) - len(screened)

    results = []
    kill_counts = {"flat_terrain": 0, "ratio_too_high": 0, "missing_coordinates_or_elevation": 0, "other": 0}
    survivors = 0

    for dam in screened:
        lat = float(dam["lat"])
        lon = float(dam["lon"])
        patch = load_dem_patch(lat, lon, search_radius_km, resolution_m=resolution_m)
        if patch is None:
            kill_counts["other"] += 1
            results.append({"dam_id": dam.get("id"), "dam_name": dam.get("name"), "viable_up": False, "viable_down": False, "kill_reason": "no_dem_data"})
            continue

        result = tier1_screen(dam, patch, config)
        result["dam_id"] = dam.get("id")
        result["dam_name"] = dam.get("name")
        result["dam_lat"] = lat
        result["dam_lon"] = lon

        if result.get("viable_up") or result.get("viable_down"):
            survivors += 1
        else:
            reason = result.get("kill_reason", "other")
            kill_counts[reason] = kill_counts.get(reason, 0) + 1

        results.append(result)

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    import orjson
    with open(DATA_PROCESSED / "siting_tier1.json", "wb") as f:
        f.write(orjson.dumps(results, option=orjson.OPT_INDENT_2 | orjson.OPT_SERIALIZE_NUMPY))

    return safe_dumps({
        "status": "ok",
        "total_dams": len(dams),
        "psh_excluded": psh_excluded,
        "tier1_input": len(screened),
        "survivors": survivors,
        "killed": len(screened) - survivors,
        "kill_reasons": kill_counts,
    })


@mcp.tool()
def generate_tier1_results() -> str:
    """Generate Tier 1 outputs: Excel dam-by-dam table and map. Requires siting_tier1.json."""
    import orjson
    import pandas as pd
    from geospatial.visualization.siting_export import generate_tier1_excel
    from geospatial.visualization.siting_map import generate_siting_map

    tier1_path = DATA_PROCESSED / "siting_tier1.json"
    if not tier1_path.exists():
        return safe_dumps({"error": "Run tier1_elevation_screen first"})

    with open(tier1_path, "rb") as f:
        tier1_results = orjson.loads(f.read())

    dams = load_dams()
    dams_df = pd.DataFrame(dams) if dams else pd.DataFrame()

    paired_dam_ids = set()
    scored_path = DATA_PROCESSED / "scored_pairs.json"
    if scored_path.exists():
        scored = pd.read_json(scored_path)
        for _, row in scored.iterrows():
            paired_dam_ids.add(row.get("upper_dam_id"))
            paired_dam_ids.add(row.get("lower_dam_id"))
        paired_dam_ids.discard(None)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {}

    try:
        excel_path = generate_tier1_excel(tier1_results)
        outputs["excel"] = str(excel_path)
    except Exception as e:
        outputs["excel_error"] = str(e)

    try:
        map_path = generate_siting_map(dams_df, tier1_results, [], paired_dam_ids)
        outputs["map"] = str(map_path)
    except Exception as e:
        outputs["map_error"] = str(e)

    survivors = sum(1 for r in tier1_results if r.get("viable_up") or r.get("viable_down"))
    return safe_dumps({
        "status": "ok",
        "tier1_survivors": survivors,
        "total_screened": len(tier1_results),
        "outputs": outputs,
    })


@mcp.tool()
def siting_scan() -> str:
    """Start basin-detection siting scan as a background process. Returns immediately. Call siting_scan_status to check progress."""
    import os
    import subprocess
    import sys

    tier1_path = DATA_PROCESSED / "siting_tier1.json"
    if not tier1_path.exists():
        return safe_dumps({"error": "Run tier1_elevation_screen first"})

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    active_file = get_active_file()
    log_path = DATA_PROCESSED / "siting_scan.log"
    pid_path = DATA_PROCESSED / "siting_scan.pid"

    if pid_path.exists():
        pid = int(pid_path.read_text().strip())
        if _pid_alive(pid):
            return safe_dumps({"status": "already_running", "pid": pid, "message": "Scan already in progress. Call siting_scan_status to check."})
        pid_path.unlink()

    script = Path(__file__).resolve().parent / "siting" / "run_scan.py"
    cwd = str(Path(__file__).resolve().parent.parent.parent)
    detach_kwargs = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
        if sys.platform == "win32"
        else {"start_new_session": True}
    )

    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, str(script), str(active_file)],
            stdout=log, stderr=log, cwd=cwd, env=env,
            **detach_kwargs,
        )
    pid_path.write_text(str(proc.pid))

    return safe_dumps({
        "status": "started",
        "pid": proc.pid,
        "log_path": str(log_path),
        "message": (
            f"Siting scan running in background. Set a Monitor on {log_path} that tails for these line patterns: "
            "'-> N candidates' (a dam produced candidates), 'DONE:' (scan complete), 'ERROR|Traceback' (failure). "
            "The Monitor is event-driven — you'll be notified as things happen. "
            "Only call siting_scan_status as a fallback if the Monitor goes silent for >10 minutes."
        ),
    })


@mcp.tool()
def siting_scan_status() -> str:
    """Check progress of a running siting scan. Returns status, last log lines, and results summary when complete."""
    pid_path = DATA_PROCESSED / "siting_scan.pid"
    log_path = DATA_PROCESSED / "siting_scan.log"
    candidates_path = DATA_PROCESSED / "siting_candidates.json"
    partial_path = DATA_PROCESSED / "siting_candidates_partial.json"

    running = False
    pid = None
    if pid_path.exists():
        pid = int(pid_path.read_text().strip())
        if _pid_alive(pid):
            running = True
        else:
            pid_path.unlink()

    last_lines = []
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        last_lines = lines[-20:]

    progress = None
    if partial_path.exists():
        with open(partial_path, "rb") as f:
            import orjson
            saved = orjson.loads(f.read())
        progress = {"dams_done": len(saved.get("done_ids", [])), "candidates_so_far": len(saved.get("candidates", []))}

    if running:
        return safe_dumps({"status": "running", "pid": pid, "progress": progress, "log_tail": last_lines})

    if candidates_path.exists():
        with open(candidates_path, "rb") as f:
            import orjson
            candidates = orjson.loads(f.read())
        beats = sum(1 for c in candidates if c.get("passes_battery_test"))
        marginal = sum(1 for c in candidates if c.get("marginal_flag") and not c.get("passes_battery_test"))
        return safe_dumps({
            "status": "complete",
            "viable_candidates": len(candidates),
            "beats_battery": beats,
            "marginal": marginal,
            "log_tail": last_lines,
        })

    return safe_dumps({"status": "not_started", "log_tail": last_lines})


@mcp.tool()
def generate_siting_results() -> str:
    """Generate siting outputs: Excel, map, terrain profiles PDF. Requires siting_candidates.json."""
    import orjson
    import pandas as pd
    from geospatial.visualization.siting_map import generate_siting_map
    from geospatial.visualization.siting_export import generate_siting_excel
    from geospatial.visualization.siting_profiles import generate_siting_profiles

    candidates_path = DATA_PROCESSED / "siting_candidates.json"
    if not candidates_path.exists():
        return safe_dumps({"error": "Run siting_scan first"})

    with open(candidates_path, "rb") as f:
        candidates = orjson.loads(f.read())

    dam_scan_kills = {}
    kills_path = DATA_PROCESSED / "siting_scan_kills.json"
    if kills_path.exists():
        with open(kills_path, "rb") as f:
            dam_scan_kills = orjson.loads(f.read())

    dams = load_dams()
    if dams is None:
        return safe_dumps({"error": "No data file selected. Call load_dam_registry first."})

    dams_df = pd.DataFrame(dams)

    tier1_results = []
    tier1_path = DATA_PROCESSED / "siting_tier1.json"
    if tier1_path.exists():
        with open(tier1_path, "rb") as f:
            tier1_results = orjson.loads(f.read())

    paired_dam_ids = set()
    scored_path = DATA_PROCESSED / "scored_pairs.json"
    if scored_path.exists():
        scored = pd.read_json(scored_path)
        for _, row in scored.iterrows():
            paired_dam_ids.add(row.get("upper_dam_id"))
            paired_dam_ids.add(row.get("lower_dam_id"))
        paired_dam_ids.discard(None)

    tier1_survivors = [r for r in tier1_results if r.get("viable_up") or r.get("viable_down")]

    funnel_summary = {
        "total_dams": len(dams),
        "paired_excluded": len(paired_dam_ids),
        "tier1_input": len(tier1_results),
        "tier1_survivors": len(tier1_survivors),
        "killed_flat": sum(1 for r in tier1_results if r.get("kill_reason") == "flat_terrain"),
        "killed_ratio": sum(1 for r in tier1_results if r.get("kill_reason") == "ratio_too_high"),
        "killed_other_t1": sum(1 for r in tier1_results if r.get("kill_reason") not in (None, "flat_terrain", "ratio_too_high") and not r.get("viable_up") and not r.get("viable_down")),
        "viable_candidates": len(candidates),
        "dams_with_candidates": len({c.get("dam_id") for c in candidates}),
        "beats_battery": sum(1 for c in candidates if c.get("passes_battery_test")),
        "marginal": sum(1 for c in candidates if c.get("marginal_flag") and not c.get("passes_battery_test")),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {}

    try:
        excel_path = generate_siting_excel(candidates, funnel_summary, dams_df, tier1_results, dam_scan_kills)
        outputs["excel"] = str(excel_path)
    except Exception as e:
        outputs["excel_error"] = str(e)

    try:
        map_path = generate_siting_map(dams_df, tier1_results, candidates, paired_dam_ids, dam_scan_kills)
        outputs["map"] = str(map_path)
    except Exception as e:
        outputs["map_error"] = str(e)

    try:
        profiles_path = generate_siting_profiles(candidates, dams_df)
        outputs["profiles"] = str(profiles_path) if profiles_path else None
    except Exception as e:
        outputs["profiles_error"] = str(e)

    return safe_dumps({
        "status": "ok",
        "candidates_count": len(candidates),
        "funnel_summary": funnel_summary,
        "outputs": outputs,
    })


if __name__ == "__main__":
    mcp.run()
