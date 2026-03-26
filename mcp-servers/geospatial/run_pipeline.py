#!/usr/bin/env python3
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geospatial.config import (
    load_config, DATA_PROCESSED, OUTPUT_EXPORTS, OUTPUT_MAPS, OUTPUT_REPORTS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(Path(__file__).resolve().parent.parent.parent / "output" / "pipeline.log")),
    ],
)
log = logging.getLogger("pipeline")


def run():
    start = time.time()
    log.info("=" * 60)
    log.info("Morocco PSH Screening Pipeline")
    log.info("=" * 60)

    config = load_config()
    log.info(f"Config loaded from parameters.json")

    log.info("\n=== Phase 1: Data Ingestion ===")

    log.info("Step 1.1: Downloading databases...")
    from geospatial.ingestion.download import download_all
    sources = download_all()
    if not sources:
        log.error("No dam databases available. See manual download instructions above.")
        log.error("Place downloaded files in data/raw/ and rerun.")
        return

    log.info(f"Available sources: {list(sources.keys())}")
    for name, df in sources.items():
        log.info(f"  {name}: {len(df)} records")

    log.info("Step 1.2: Merging and deduplicating...")
    from geospatial.ingestion.merge import merge_registries
    registry = merge_registries(sources)
    log.info(f"Unified registry: {len(registry)} dams")
    registry.to_json(DATA_PROCESSED / "dam_registry_raw.json", orient="records", indent=2)

    log.info("Step 1.3: Enriching with SRTM elevation...")
    from geospatial.ingestion.elevate import enrich_dam_elevations
    registry = enrich_dam_elevations(registry)
    registry.to_json(DATA_PROCESSED / "dam_registry.json", orient="records", indent=2)

    missing_elev = registry["elevation_wall_m"].isna().sum()
    log.info(f"Elevation coverage: {len(registry) - missing_elev}/{len(registry)} dams")

    log.info("\n=== Phase 2: Pair Screening ===")

    log.info("Step 2.1: Generating all pairs...")
    from geospatial.screening.pairs import generate_pairs
    all_pairs = generate_pairs(registry)
    log.info(f"Total pairs generated: {len(all_pairs)}")

    log.info("Step 2.2: Applying Tier 1 filters...")
    from geospatial.screening.filters import apply_tier1_filters, apply_tier2_filters
    filtered = apply_tier1_filters(all_pairs)

    tier1_viable = filtered[filtered["tier1_status"].isin(["pass", "borderline"])]
    log.info(f"Tier 1 survivors: {len(tier1_viable)}")

    log.info("Step 2.3: Applying Tier 2 filters...")
    filtered = apply_tier2_filters(filtered)
    filtered.to_json(DATA_PROCESSED / "filtered_pairs.json", orient="records", indent=2)

    status_col = "tier2_status" if "tier2_status" in filtered.columns else "tier1_status"
    viable = filtered[filtered[status_col].isin(["pass", "borderline"])].copy()
    log.info(f"Tier 2 survivors: {len(viable)}")

    if len(viable) == 0:
        log.warning("No viable pairs found. Generating outputs with available data.")
        _generate_final_outputs(registry, filtered, None, None)
        return

    log.info("\n=== Phase 3: Terrain Analysis ===")

    log.info("Step 3.1: Analyzing terrain for viable pairs...")
    from geospatial.terrain.profiles import analyze_all_pairs
    terrain_analyzed = analyze_all_pairs(viable)

    terrain_save = terrain_analyzed.drop(columns=["terrain_profile"], errors="ignore")
    terrain_save.to_json(DATA_PROCESSED / "terrain_analyzed.json", orient="records", indent=2)

    profiles = {}
    for _, pair in terrain_analyzed.iterrows():
        key = f"{pair.get('upper_dam_id')}_{pair.get('lower_dam_id')}"
        profile = pair.get("terrain_profile")
        if profile:
            profiles[key] = profile
    with open(DATA_PROCESSED / "terrain_profiles.json", "w") as f:
        json.dump(profiles, f, default=str)

    feasible = terrain_analyzed[terrain_analyzed["terrain_difficulty"] != "infeasible"].copy()
    log.info(f"Terrain feasible: {len(feasible)}")

    if len(feasible) == 0:
        log.warning("No terrain-feasible pairs. Generating outputs with available data.")
        _generate_final_outputs(registry, filtered, None, None)
        return

    log.info("\n=== Phase 4: Energy and Cost Analysis ===")

    log.info("Step 4.1: Calculating energy potential...")
    from geospatial.scoring.energy import calculate_all_energies
    with_energy = calculate_all_energies(feasible)

    log.info("Step 4.2: Comparing costs vs battery storage...")
    from geospatial.scoring.cost import calculate_all_costs
    with_costs = calculate_all_costs(with_energy)

    log.info("Step 4.3: Composite scoring...")
    from geospatial.scoring.composite import score_pairs, run_sensitivity
    scored = score_pairs(with_costs)
    scored.to_json(DATA_PROCESSED / "scored_pairs.json", orient="records", indent=2)

    log.info("Step 4.4: Sensitivity analysis...")
    sensitivity = run_sensitivity(with_costs)
    with open(DATA_PROCESSED / "sensitivity_results.json", "w") as f:
        json.dump(sensitivity, f, indent=2, default=str)

    log.info("\n=== Phase 5: Output Generation ===")
    _generate_final_outputs(registry, filtered, scored, sensitivity)

    elapsed = time.time() - start
    log.info(f"\n{'=' * 60}")
    log.info(f"Pipeline complete in {elapsed:.0f}s")
    log.info(f"{'=' * 60}")

    _print_summary(registry, all_pairs, filtered, scored)


def _generate_final_outputs(registry, filtered, scored, sensitivity):
    log.info("Generating maps...")
    from geospatial.visualization.maps import (
        generate_dam_registry_map,
        generate_pairs_map,
        generate_top_pairs_detail_map,
    )
    generate_dam_registry_map(registry, filtered)

    if scored is not None and len(scored) > 0:
        generate_pairs_map(registry, scored)
        generate_top_pairs_detail_map(scored, registry)

        log.info("Generating terrain profile charts...")
        from geospatial.visualization.terrain_viz import generate_all_terrain_charts

        profiles_path = DATA_PROCESSED / "terrain_profiles.json"
        if profiles_path.exists():
            with open(profiles_path) as f:
                profiles = json.load(f)
            for i, row in scored.iterrows():
                key = f"{row.get('upper_dam_id')}_{row.get('lower_dam_id')}"
                if key in profiles:
                    scored.at[i, "terrain_profile"] = profiles[key]
            generate_all_terrain_charts(scored)

    log.info("Generating export files...")
    from geospatial.visualization.export import generate_all_outputs
    generate_all_outputs(registry, filtered, scored, sensitivity)


def _print_summary(registry, all_pairs, filtered, scored):
    log.info("\n=== RESULTS SUMMARY ===")
    log.info(f"Total dams in registry: {len(registry)}")
    log.info(f"Total pairs evaluated: {len(all_pairs)}")

    status_col = "tier2_status" if "tier2_status" in filtered.columns else "tier1_status"
    viable = filtered[filtered[status_col].isin(["pass", "borderline"])]
    log.info(f"Viable pairs after filtering: {len(viable)}")

    if scored is not None and len(scored) > 0:
        log.info(f"Scored/ranked pairs: {len(scored)}")
        log.info(f"\nTop 10 pairs:")
        for _, pair in scored.head(10).iterrows():
            log.info(
                f"  #{pair.get('rank', '')}: "
                f"{pair.get('upper_dam_name', '')} - {pair.get('lower_dam_name', '')} | "
                f"Head: {pair.get('head_m', 'N/A')}m | "
                f"Dist: {pair.get('distance_km', 'N/A')}km | "
                f"Energy: {pair.get('energy_mwh_standard', 'N/A')} MWh | "
                f"Score: {pair.get('composite_score', 0):.3f}"
            )

    log.info(f"\nOutput files:")
    log.info(f"  Excel:   output/exports/psh_screening_results.xlsx")
    log.info(f"  JSON:    output/exports/psh_screening_results.json")
    log.info(f"  Map:     output/maps/morocco_overview.html")
    log.info(f"  Pairs:   output/maps/top_pairs.html")
    log.info(f"  KML:     output/maps/morocco_dams.kml")
    log.info(f"  GeoJSON: output/maps/morocco_pairs.geojson")


if __name__ == "__main__":
    run()
