# /screen-dams

Screen all dams in a target country for pumped storage hydropower potential.

## Usage

```
/screen-dams [country]
```

Default country: Morocco.

## Prerequisites

- Python 3.10+ with venv
- Internet access (for downloading databases and SRTM tiles)
- `config/parameters.json` configured with desired thresholds

## What This Command Does

This is the main end-to-end screening workflow. It orchestrates the MCP geospatial tools in sequence:

### Phase 1: Data Ingestion
1. Load skills: methodology, data-sources, constraints
2. Call `download_databases` tool to fetch HydroLAKES, GRanD, GDAT, FAO AQUASTAT
3. Call `merge_registries` tool to fuzzy-match and deduplicate into unified registry
4. Call `enrich_elevation` tool to add SRTM elevation at wall, centroid, pour point
5. Output: `data/processed/dam_registry.json`
6. Call `generate_map` tool to create registry overview map

### Phase 2: Pair Screening
7. Call `generate_pairs` tool to create all possible dam pair combinations
8. Call `filter_pairs` tool with Tier 1 constraints (head, distance ratio, capacity)
9. Call `filter_pairs` tool with Tier 2 constraints (protected areas, fill rate, grid proximity)
10. Review borderline cases: examine pairs near thresholds, write rationales
11. Output: `data/processed/filtered_pairs.json`

### Phase 3: Terrain Analysis
12. Call `analyze_terrain` tool for each viable pair (elevation profiles, obstacles)
13. Classify terrain difficulty, estimate tunnel lengths
14. Eliminate pairs with infeasible terrain
15. Output: terrain profiles in `output/reports/`

### Phase 4: Scoring and Output
16. Call `calculate_energy` tool for each terrain-viable pair at 3 fill levels
17. Call `compare_costs` tool for PSH vs battery benchmark
18. Call `score_pairs` tool with composite scoring across dimensions
19. Call `run_sensitivity` tool with tight/standard/relaxed thresholds
20. Call `generate_outputs` tool: Excel workbook, interactive maps, JSON, KML, GeoJSON
21. Output: everything in `output/`

### Phase 5: Summary
22. Present top 10 pairs with key metrics
23. Summary statistics: how many dams, pairs evaluated, pairs viable
24. Flag any data quality issues or missing data
25. Recommend whether Package 2 (new dam site scanning) is needed

## After Running

The agent will have produced:
- `output/exports/dam_registry.xlsx` (or .json)
- `output/exports/ranked_pairs.xlsx` (or .json)
- `output/maps/morocco_overview.html`
- `output/maps/top_pairs.html`
- `output/maps/morocco_dams.kml`
- `output/maps/morocco_pairs.geojson`
- `output/reports/terrain_profile_*.html` (per top pair)

CEB team can open HTML maps in browser, KML in Google Earth, GeoJSON in QGIS.

To rerun with different parameters: edit `config/parameters.json` and run again.
