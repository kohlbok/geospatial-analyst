import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

from geospatial.config import (
    load_config, reload_config, DATA_PROCESSED,
    OUTPUT_EXPORTS, OUTPUT_MAPS, OUTPUT_REPORTS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("psh-screening")

mcp = FastMCP("PSH Screening")


@mcp.tool()
def download_databases() -> str:
    """Download and parse all four dam databases (GRanD, GDAT, HydroLAKES, FAO AQUASTAT), filtered to Morocco."""
    from geospatial.ingestion.download import download_all
    sources = download_all()
    summary = {name: len(df) for name, df in sources.items()}
    _save_intermediate("raw_sources", {name: df.to_dict("records") for name, df in sources.items()})
    return json.dumps({"status": "ok", "sources": summary})


@mcp.tool()
def merge_registries() -> str:
    """Merge and deduplicate dam records from all sources into a unified registry using coordinate proximity (500m) and fuzzy name matching."""
    from geospatial.ingestion.download import download_all
    from geospatial.ingestion.merge import merge_registries as do_merge

    cached = _load_intermediate("raw_sources")
    if cached:
        import pandas as pd
        sources = {name: pd.DataFrame(records) for name, records in cached.items()}
    else:
        sources = download_all()

    registry = do_merge(sources)
    registry.to_json(DATA_PROCESSED / "dam_registry_raw.json", orient="records", indent=2)
    return json.dumps({
        "status": "ok",
        "total_dams": len(registry),
        "sample": registry.head(5).to_dict("records"),
    }, default=str)


@mcp.tool()
def enrich_elevation() -> str:
    """Add SRTM 30m elevation data to each dam in the registry (wall and centroid elevations)."""
    import pandas as pd
    from geospatial.ingestion.elevate import enrich_dam_elevations

    registry_path = DATA_PROCESSED / "dam_registry_raw.json"
    if not registry_path.exists():
        return json.dumps({"error": "Run merge_registries first"})

    registry = pd.read_json(registry_path)
    enriched = enrich_dam_elevations(registry)
    enriched.to_json(DATA_PROCESSED / "dam_registry.json", orient="records", indent=2)

    missing = enriched["elevation_wall_m"].isna().sum()
    return json.dumps({
        "status": "ok",
        "total_dams": len(enriched),
        "elevation_coverage": f"{len(enriched) - missing}/{len(enriched)}",
    })


@mcp.tool()
def generate_pairs() -> str:
    """Generate all possible dam pair combinations with elevation difference and distance calculations."""
    import pandas as pd
    from geospatial.screening.pairs import generate_pairs as do_generate

    registry = _load_registry()
    if registry is None:
        return json.dumps({"error": "Run enrich_elevation first"})

    pairs = do_generate(registry)
    pairs.to_json(DATA_PROCESSED / "all_pairs.json", orient="records", indent=2)
    return json.dumps({
        "status": "ok",
        "total_pairs": len(pairs),
        "head_range": f"{pairs['head_m'].min()}-{pairs['head_m'].max()}m" if len(pairs) > 0 else "N/A",
    })


@mcp.tool()
def filter_pairs(tier: str = "all") -> str:
    """Apply engineering constraint filters to dam pairs. tier='1' for fast filters only, '2' for deep filters, 'all' for both."""
    import pandas as pd
    from geospatial.screening.filters import apply_tier1_filters, apply_tier2_filters

    pairs_path = DATA_PROCESSED / "all_pairs.json"
    if not pairs_path.exists():
        return json.dumps({"error": "Run generate_pairs first"})

    pairs = pd.read_json(pairs_path)

    if tier in ("1", "all"):
        pairs = apply_tier1_filters(pairs)

    if tier in ("2", "all"):
        registry = _load_registry()
        pairs = apply_tier2_filters(pairs, registry)

    pairs.to_json(DATA_PROCESSED / "filtered_pairs.json", orient="records", indent=2)

    status_col = "tier2_status" if "tier2_status" in pairs.columns else "tier1_status"
    viable = pairs[pairs[status_col].isin(["pass", "borderline"])]
    return json.dumps({
        "status": "ok",
        "total_evaluated": len(pairs),
        "viable": len(viable),
        "failed": len(pairs) - len(viable),
    })


@mcp.tool()
def analyze_terrain() -> str:
    """Run terrain analysis (elevation profiles, obstacles, tunnel estimation) for all viable pairs."""
    import pandas as pd
    from geospatial.terrain.profiles import analyze_all_pairs

    filtered_path = DATA_PROCESSED / "filtered_pairs.json"
    if not filtered_path.exists():
        return json.dumps({"error": "Run filter_pairs first"})

    pairs = pd.read_json(filtered_path)
    status_col = "tier2_status" if "tier2_status" in pairs.columns else "tier1_status"
    viable = pairs[pairs[status_col].isin(["pass", "borderline"])].copy()

    if len(viable) == 0:
        return json.dumps({"status": "ok", "message": "No viable pairs to analyze"})

    analyzed = analyze_all_pairs(viable)
    terrain_feasible = analyzed[analyzed["terrain_difficulty"] != "infeasible"]

    save_df = analyzed.drop(columns=["terrain_profile"], errors="ignore")
    save_df.to_json(DATA_PROCESSED / "terrain_analyzed.json", orient="records", indent=2)

    profiles = {}
    for _, pair in analyzed.iterrows():
        key = f"{pair.get('upper_dam_id')}_{pair.get('lower_dam_id')}"
        profile = pair.get("terrain_profile")
        if profile:
            profiles[key] = profile
    with open(DATA_PROCESSED / "terrain_profiles.json", "w") as f:
        json.dump(profiles, f, default=str)

    return json.dumps({
        "status": "ok",
        "analyzed": len(analyzed),
        "feasible": len(terrain_feasible),
        "infeasible": len(analyzed) - len(terrain_feasible),
        "difficulty_breakdown": analyzed["terrain_difficulty"].value_counts().to_dict(),
    })


@mcp.tool()
def calculate_energy() -> str:
    """Calculate energy potential for all terrain-feasible pairs at three fill levels."""
    import pandas as pd
    from geospatial.scoring.energy import calculate_all_energies

    terrain_path = DATA_PROCESSED / "terrain_analyzed.json"
    if not terrain_path.exists():
        return json.dumps({"error": "Run analyze_terrain first"})

    pairs = pd.read_json(terrain_path)
    feasible = pairs[pairs["terrain_difficulty"] != "infeasible"].copy()

    if len(feasible) == 0:
        return json.dumps({"status": "ok", "message": "No feasible pairs"})

    with_energy = calculate_all_energies(feasible)
    with_energy.to_json(DATA_PROCESSED / "energy_calculated.json", orient="records", indent=2)

    return json.dumps({
        "status": "ok",
        "pairs_with_energy": len(with_energy),
        "energy_range_mwh": {
            "min": with_energy["energy_mwh_standard"].min(),
            "max": with_energy["energy_mwh_standard"].max(),
            "median": with_energy["energy_mwh_standard"].median(),
        },
    }, default=str)


@mcp.tool()
def compare_costs() -> str:
    """Compare PSH costs against battery storage benchmark for all pairs."""
    import pandas as pd
    from geospatial.scoring.cost import calculate_all_costs

    energy_path = DATA_PROCESSED / "energy_calculated.json"
    if not energy_path.exists():
        return json.dumps({"error": "Run calculate_energy first"})

    pairs = pd.read_json(energy_path)
    with_costs = calculate_all_costs(pairs)
    with_costs.to_json(DATA_PROCESSED / "cost_compared.json", orient="records", indent=2)

    cheaper = with_costs["psh_cheaper"].sum() if "psh_cheaper" in with_costs.columns else 0
    return json.dumps({
        "status": "ok",
        "total_pairs": len(with_costs),
        "psh_cheaper": int(cheaper),
        "battery_cheaper": int(len(with_costs) - cheaper),
    })


@mcp.tool()
def score_pairs(weight_variant: str = "default") -> str:
    """Apply composite scoring to all pairs and produce ranked list. weight_variant: 'default', 'cost_focused', or 'energy_focused'."""
    import pandas as pd
    from geospatial.scoring.composite import score_pairs as do_score

    cost_path = DATA_PROCESSED / "cost_compared.json"
    if not cost_path.exists():
        return json.dumps({"error": "Run compare_costs first"})

    pairs = pd.read_json(cost_path)
    scored = do_score(pairs, weight_variant=weight_variant)
    scored.to_json(DATA_PROCESSED / "scored_pairs.json", orient="records", indent=2)

    config = load_config()
    top_n = config["output"]["top_n_detailed"]
    top = scored.head(top_n)[["rank", "upper_dam_name", "lower_dam_name", "head_m",
                               "distance_km", "energy_mwh_standard", "composite_score"]].to_dict("records")

    return json.dumps({
        "status": "ok",
        "total_scored": len(scored),
        "top_pairs": top,
    }, default=str)


@mcp.tool()
def run_sensitivity() -> str:
    """Run sensitivity analysis with tight/standard/relaxed parameters and multiple weight distributions."""
    import pandas as pd
    from geospatial.scoring.composite import run_sensitivity as do_sensitivity

    cost_path = DATA_PROCESSED / "cost_compared.json"
    pairs_path = DATA_PROCESSED / "all_pairs.json"
    if not cost_path.exists():
        return json.dumps({"error": "Run compare_costs first"})

    scored_pairs = pd.read_json(cost_path)
    all_pairs = pd.read_json(pairs_path) if pairs_path.exists() else scored_pairs

    results = do_sensitivity(scored_pairs)

    with open(DATA_PROCESSED / "sensitivity_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    return json.dumps({"status": "ok", "scenarios": list(results.keys())}, default=str)


@mcp.tool()
def generate_maps() -> str:
    """Generate interactive Folium HTML maps: overview map and top pairs map."""
    import pandas as pd
    from geospatial.visualization.maps import (
        generate_dam_registry_map,
        generate_pairs_map,
        generate_top_pairs_detail_map,
    )

    registry = _load_registry()
    if registry is None:
        return json.dumps({"error": "No dam registry found"})

    scored_path = DATA_PROCESSED / "scored_pairs.json"
    scored = pd.read_json(scored_path) if scored_path.exists() else None

    filtered_path = DATA_PROCESSED / "filtered_pairs.json"
    filtered = pd.read_json(filtered_path) if filtered_path.exists() else None

    paths = {}
    paths["overview"] = generate_dam_registry_map(registry, filtered)

    if scored is not None and len(scored) > 0:
        paths["pairs"] = generate_pairs_map(registry, scored)
        paths["detail"] = generate_top_pairs_detail_map(scored, registry)

    return json.dumps({"status": "ok", "maps": paths})


@mcp.tool()
def generate_terrain_charts() -> str:
    """Generate terrain profile charts for top-ranked pairs."""
    import pandas as pd
    from geospatial.visualization.terrain_viz import generate_all_terrain_charts

    scored_path = DATA_PROCESSED / "scored_pairs.json"
    profiles_path = DATA_PROCESSED / "terrain_profiles.json"

    if not scored_path.exists():
        return json.dumps({"error": "Run score_pairs first"})

    scored = pd.read_json(scored_path)

    if profiles_path.exists():
        with open(profiles_path) as f:
            profiles = json.load(f)

        for i, row in scored.iterrows():
            key = f"{row.get('upper_dam_id')}_{row.get('lower_dam_id')}"
            if key in profiles:
                scored.at[i, "terrain_profile"] = profiles[key]

    config = load_config()
    max_charts = config["output"].get("top_n_terrain_profiles", 20)
    paths = generate_all_terrain_charts(scored, max_charts=max_charts)

    return json.dumps({"status": "ok", "charts_generated": len(paths), "paths": paths})


@mcp.tool()
def generate_outputs() -> str:
    """Generate all output files: Excel workbook, JSON export, KML/KMZ, GeoJSON."""
    import pandas as pd
    from geospatial.visualization.export import generate_all_outputs

    registry = _load_registry()
    if registry is None:
        return json.dumps({"error": "No dam registry found"})

    all_pairs_path = DATA_PROCESSED / "filtered_pairs.json"
    all_pairs = pd.read_json(all_pairs_path) if all_pairs_path.exists() else None

    scored_path = DATA_PROCESSED / "scored_pairs.json"
    scored = pd.read_json(scored_path) if scored_path.exists() else None

    sens_path = DATA_PROCESSED / "sensitivity_results.json"
    sensitivity = None
    if sens_path.exists():
        with open(sens_path) as f:
            sensitivity = json.load(f)

    paths = generate_all_outputs(registry, all_pairs, scored, sensitivity)
    return json.dumps({"status": "ok", "outputs": paths})


@mcp.tool()
def run_full_pipeline() -> str:
    """Run the complete PSH screening pipeline end-to-end: download, merge, elevate, pair, filter, terrain, energy, cost, score, output."""
    steps = [
        ("Downloading databases", download_databases),
        ("Merging registries", merge_registries),
        ("Enriching elevation", enrich_elevation),
        ("Generating pairs", generate_pairs),
        ("Filtering pairs", lambda: filter_pairs("all")),
        ("Analyzing terrain", analyze_terrain),
        ("Calculating energy", calculate_energy),
        ("Comparing costs", compare_costs),
        ("Scoring pairs", lambda: score_pairs("default")),
        ("Running sensitivity", run_sensitivity),
        ("Generating maps", generate_maps),
        ("Generating terrain charts", generate_terrain_charts),
        ("Generating outputs", generate_outputs),
    ]

    results = {}
    for step_name, step_fn in steps:
        log.info(f"=== {step_name} ===")
        try:
            result = step_fn()
            results[step_name] = json.loads(result)
            if results[step_name].get("error"):
                log.error(f"Step failed: {step_name} - {results[step_name]['error']}")
                break
        except Exception as e:
            log.error(f"Step failed: {step_name} - {e}")
            results[step_name] = {"error": str(e)}
            break

    return json.dumps({"status": "ok", "pipeline_results": results}, default=str)


def _load_registry():
    import pandas as pd
    registry_path = DATA_PROCESSED / "dam_registry.json"
    if registry_path.exists():
        return pd.read_json(registry_path)
    raw_path = DATA_PROCESSED / "dam_registry_raw.json"
    if raw_path.exists():
        return pd.read_json(raw_path)
    return None


def _save_intermediate(name, data):
    path = DATA_PROCESSED / f"_intermediate_{name}.json"
    with open(path, "w") as f:
        json.dump(data, f, default=str)


def _load_intermediate(name):
    path = DATA_PROCESSED / f"_intermediate_{name}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    mcp.run()
