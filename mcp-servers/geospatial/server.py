import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

from geospatial.config import (
    load_config, reload_config, load_dams,
    DAMS_INPUT, DATA_PROCESSED, OUTPUT_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("psh-screening")

mcp = FastMCP("PSH Screening")


@mcp.tool()
def load_dam_registry() -> str:
    """Load the dam registry from data/dams.json. Returns dam count and sample data."""
    dams = load_dams()
    if dams is None:
        return json.dumps({"error": "No data/dams.json found. Place your dam data file there first."})
    return json.dumps({
        "status": "ok",
        "total_dams": len(dams),
        "sample": dams[:3],
    }, default=str)


@mcp.tool()
def generate_pairs() -> str:
    """Generate all possible dam pair combinations with head and distance calculations."""
    import pandas as pd
    from geospatial.screening.pairs import generate_pairs as do_generate

    dams = load_dams()
    if dams is None:
        return json.dumps({"error": "No data/dams.json found"})

    registry = pd.DataFrame(dams)
    registry["elevation_wall_m"] = registry["elevation_m"]

    pairs = do_generate(registry)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    pairs.to_json(DATA_PROCESSED / "all_pairs.json", orient="records", indent=2, default_handler=str)

    return json.dumps({
        "status": "ok",
        "total_pairs": len(pairs),
        "head_range": f"{pairs['head_m'].min():.0f}-{pairs['head_m'].max():.0f}m" if len(pairs) > 0 else "N/A",
        "distance_range": f"{pairs['distance_km'].min():.1f}-{pairs['distance_km'].max():.1f}km" if len(pairs) > 0 else "N/A",
    })


@mcp.tool()
def screen_pairs() -> str:
    """Apply screening filters and score all pairs. Returns ranked list."""
    import pandas as pd
    from geospatial.screening.filters import apply_tier1_filters
    from geospatial.scoring.energy import calculate_all_energies
    from geospatial.scoring.cost import calculate_all_costs
    from geospatial.scoring.composite import score_pairs as do_score

    pairs_path = DATA_PROCESSED / "all_pairs.json"
    if not pairs_path.exists():
        return json.dumps({"error": "Run generate_pairs first"})

    pairs = pd.read_json(pairs_path)
    config = load_config()

    filtered = apply_tier1_filters(pairs)
    viable = filtered[filtered["tier1_status"].isin(["pass", "borderline"])].copy()

    if len(viable) == 0:
        return json.dumps({"status": "ok", "viable_pairs": 0, "message": "No pairs passed filters"})

    with_energy = calculate_all_energies(viable)
    with_costs = calculate_all_costs(with_energy)
    scored = do_score(with_costs)

    scored.to_json(DATA_PROCESSED / "scored_pairs.json", orient="records", indent=2, default_handler=str)
    filtered.to_json(DATA_PROCESSED / "filtered_pairs.json", orient="records", indent=2, default_handler=str)

    top = scored.head(10)
    top_list = []
    for _, row in top.iterrows():
        top_list.append({
            "rank": int(row.get("rank", 0)),
            "upper_dam": row.get("upper_dam_name", "?"),
            "lower_dam": row.get("lower_dam_name", "?"),
            "head_m": round(row.get("head_m", 0)),
            "distance_km": round(row.get("distance_km", 0), 1),
            "energy_mwh": round(row.get("energy_mwh_standard", 0)),
            "score": round(row.get("composite_score", 0), 3),
        })

    return json.dumps({
        "status": "ok",
        "total_evaluated": len(pairs),
        "viable_pairs": len(viable),
        "scored_pairs": len(scored),
        "top_10": top_list,
    }, default=str)


@mcp.tool()
def generate_map() -> str:
    """Generate a single interactive HTML map showing all dams and top pairs."""
    import pandas as pd
    from geospatial.visualization.maps import generate_combined_map

    dams = load_dams()
    if dams is None:
        return json.dumps({"error": "No data/dams.json found"})

    scored_path = DATA_PROCESSED / "scored_pairs.json"
    scored = pd.read_json(scored_path) if scored_path.exists() else None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    map_path = generate_combined_map(pd.DataFrame(dams), scored)
    return json.dumps({"status": "ok", "map": str(map_path)})


@mcp.tool()
def generate_results() -> str:
    """Generate final output files: results.xlsx, results.json, pairs.kml, pairs.geojson."""
    import pandas as pd
    from geospatial.visualization.export import generate_clean_outputs

    dams = load_dams()
    if dams is None:
        return json.dumps({"error": "No data/dams.json found"})

    scored_path = DATA_PROCESSED / "scored_pairs.json"
    if not scored_path.exists():
        return json.dumps({"error": "Run screen_pairs first"})

    scored = pd.read_json(scored_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = generate_clean_outputs(pd.DataFrame(dams), scored)
    return json.dumps({"status": "ok", "outputs": paths})


@mcp.tool()
def generate_executive_summary(expert_review: str) -> str:
    """Generate a PDF executive summary report. expert_review is a JSON list of pair assessments, each with: rank, upper_dam, lower_dam, head_m, distance_km, energy_mwh, score, grid_distance_km, verdict, assessment."""
    from datetime import datetime

    dams = load_dams()
    if dams is None:
        return json.dumps({"error": "No data/dams.json found"})

    scored_path = DATA_PROCESSED / "scored_pairs.json"
    if not scored_path.exists():
        return json.dumps({"error": "Run screen_pairs first"})

    import pandas as pd
    scored = pd.read_json(scored_path)
    config = load_config()

    pairs_data = json.loads(expert_review) if isinstance(expert_review, str) else expert_review

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
            f"minimum {config['filters']['min_capacity_mcm']} MCM capacity) and were scored across energy potential, "
            f"cost competitiveness, grid proximity, and reservoir quality."
        ),
        "min_head_m": config["filters"]["min_head_m"],
        "max_distance_km": config["filters"]["max_distance_km"],
        "min_capacity_mcm": config["filters"]["min_capacity_mcm"],
        "battery_cost": config["cost_benchmarks"]["battery_usd_per_mwh"],
        "psh_low": config["cost_benchmarks"]["psh_usd_per_mwh_low"],
        "psh_high": config["cost_benchmarks"]["psh_usd_per_mwh_high"],
        "efficiency": int(config["physics"]["round_trip_efficiency"] * 100),
        "weights": config["scoring_weights"],
        "pairs": pairs_data,
    }

    data_path = OUTPUT_DIR / "report_data.json"
    with open(data_path, "w") as f:
        json.dump(report_data, f, indent=2, default=str)

    pdf_path = OUTPUT_DIR / "executive-summary.pdf"
    try:
        from jinja2 import Template
        from weasyprint import HTML

        project_root = Path(__file__).resolve().parent.parent.parent
        template_path = project_root / "templates" / "executive-summary.html"

        with open(template_path) as f:
            template = Template(f.read())

        rendered = template.render(**report_data)

        html_output = pdf_path.with_suffix(".html")
        html_output.write_text(rendered)

        HTML(string=rendered, base_url=str(template_path.parent)).write_pdf(str(pdf_path))

        return json.dumps({"status": "ok", "pdf": str(pdf_path), "html": str(html_output)})
    except ImportError:
        return json.dumps({"error": "WeasyPrint not installed. Run: pip install jinja2 weasyprint"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def download_file(url: str, filename: str, subfolder: str = "") -> str:
    """Download any file from a URL to data/.cache/raw/{subfolder}/{filename}."""
    from geospatial.ingestion.download import _download_file, _download_and_extract_zip
    from geospatial.config import DATA_RAW
    import io, zipfile

    dest_dir = DATA_RAW / subfolder if subfolder else DATA_RAW
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename

    if filename.endswith(".zip"):
        extract_dir = dest_dir / filename.replace(".zip", "")
        success = _download_and_extract_zip(url, extract_dir, filename)
        if success:
            files = [str(f.relative_to(extract_dir)) for f in extract_dir.rglob("*") if f.is_file()][:20]
            return json.dumps({"status": "ok", "extracted_to": str(extract_dir), "files": files})
        return json.dumps({"error": f"Failed to download {url}"})

    success = _download_file(url, dest, filename)
    if success:
        return json.dumps({"status": "ok", "path": str(dest), "size_bytes": dest.stat().st_size})
    return json.dumps({"error": f"Failed to download {url}"})


@mcp.tool()
def inspect_file(path: str, max_rows: int = 20) -> str:
    """Inspect any tabular file (CSV, Excel, Shapefile, GeoJSON). Returns columns, sample rows."""
    from geospatial.ingestion.inspect import inspect_file as do_inspect
    return json.dumps(do_inspect(path, max_rows), default=str)


@mcp.tool()
def parse_tabular(path: str, column_mapping: str, filters: str = "[]", output_name: str = "parsed") -> str:
    """Parse a tabular file with agent-provided column mapping. column_mapping is JSON dict, filters is JSON list."""
    from geospatial.ingestion.parse import parse_tabular as do_parse
    mapping = json.loads(column_mapping) if isinstance(column_mapping, str) else column_mapping
    filt = json.loads(filters) if isinstance(filters, str) else filters
    return json.dumps(do_parse(path, mapping, filt, output_name), default=str)


@mcp.tool()
def enrich_grid_distance(max_workers: int = 3) -> str:
    """Look up nearest power substation (OpenStreetMap) for each dam. Adds grid_distance_km to dams.json. Runs in parallel."""
    from geospatial.ingestion.osm import enrich_dams_with_grid

    dams = load_dams()
    if dams is None:
        return json.dumps({"error": "No data/dams.json found"})

    already = sum(1 for d in dams if d.get("grid_distance_km") is not None)
    if already == len(dams):
        return json.dumps({"status": "ok", "message": "All dams already have grid distance", "total": len(dams)})

    enriched = enrich_dams_with_grid(dams, max_workers=max_workers)

    with open(str(DAMS_INPUT), "w") as f:
        json.dump(enriched, f, indent=2, default=str)

    with_grid = sum(1 for d in enriched if d.get("grid_distance_km") is not None)
    avg_dist = sum(d["grid_distance_km"] for d in enriched if d.get("grid_distance_km")) / max(with_grid, 1)

    return json.dumps({
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
        return json.dumps({"error": "No data/dams.json found"})

    registry = pd.DataFrame(dams)
    enriched = enrich_dam_elevations(registry)

    result_dams = enriched.to_dict("records")
    with open(DAMS_INPUT, "w") as f:
        json.dump(result_dams, f, indent=2, default=str)

    missing = enriched["elevation_wall_m"].isna().sum()
    return json.dumps({
        "status": "ok",
        "total_dams": len(enriched),
        "elevation_coverage": f"{len(enriched) - missing}/{len(enriched)}",
    })


if __name__ == "__main__":
    mcp.run()
