# /collect-dams

Collect dam and water body data for a country from global databases and user-provided sources.

## Platform

Before doing anything else, run `uname` once to decide which interface to use for the rest of this command:
- Output starts with `Darwin` or `Linux`: use the `mcp__geospatial__*` tools as written below.
- Output contains `MINGW`, `MSYS`, `CYGWIN`, `Windows_NT`, or `uname` is not found: the MCP server is unreliable on Windows. Use the CLI fallback instead. Every MCP tool below has an exact CLI equivalent:

  ```
  .venv/Scripts/python.exe mcp-servers/geospatial/cli.py <tool_name> [--arg value ...]
  ```

  Subcommand names match MCP tool names exactly. Keyword args become `--name value` flags. JSON output is printed to stdout — parse it the same as the MCP response. Examples:
  - `mcp__geospatial__download_file(url="...", filename="x.zip")` → `... cli.py download_file --url ... --filename x.zip`
  - `mcp__geospatial__parse_tabular(path=..., column_mapping='{"name":"Dam"}', output_name="grand")` → `... cli.py parse_tabular --path ... --column_mapping '{"name":"Dam"}' --output_name grand`
  - `mcp__geospatial__merge_sources()` → `... cli.py merge_sources`

  For each step below, translate every `mcp__geospatial__<tool>(args...)` call into the equivalent CLI invocation.

## Skills

Load: data-sources, data-collection-workflow, visual-review

## Steps

### Step 1: Setup

Read `config/parameters.json` for country name and ingestion settings. The country boundary polygon is loaded automatically from Natural Earth data (downloaded once and cached). Report:
- Country: [name]
- Proximity threshold: [X]m (water bodies closer than this are merged as duplicates)

### Step 2: Sources

Tell the user which global databases will be checked:
- **FAO AQUASTAT**: Dam names, height, capacity, purpose (Excel per country)
- **GeoDAR + GRanD**: Cross-validated coordinates, structural data (Zenodo CSV)
- **HydroLAKES**: All water bodies -- lakes, reservoirs, everything (shapefile, large download)
- **ICOLD**: Large dam register (if accessible for the country)
- **GDW / GOODD**: Satellite-derived coordinates for cross-validation
- **Under-construction**: WikiData + OSM for planned/under-construction dams

Then ask: "Know any additional sources? Government portals, spreadsheets, URLs?"

### Step 3: Download and Stage

Download each source using `download_file` MCP tool. Use the URLs from the data-sources skill. For each:
- Report success/failure immediately
- If a download fails, note it and continue with the others
- If the user provided additional URLs, download those too

Also call `fetch_under_construction` MCP tool to get planned/under-construction dams from WikiData and OSM. These are automatically staged.

Report summary: "Downloaded X/Y sources. [Failed: Z -- reason]"

### Step 4: Parse

For each downloaded source:
1. Call `inspect_file` MCP tool to see columns, dtypes, sample rows
2. Determine the column mapping (which source columns map to: name, lat, lon, height_m, capacity_mcm, surface_area_km2, year_built, etc.)
3. Call `parse_tabular` MCP tool with the mapping, a country filter (`{"type": "country", "lat_col": "<lat column>", "lon_col": "<lon column>"}`), and an appropriate output_name (e.g. "fao", "grand", "geodar", "hydrolakes")

For HydroLAKES: do NOT filter by Lake_type. Include all water bodies (lakes, reservoirs, everything). The screening step will handle viability.

For GeoDAR: values of -999 mean null. After parsing, clean these by setting any -999 capacity values to null.

Report per source: "[source]: parsed X records (Y with coordinates, Z with capacity)"

### Step 5: Review Staged

Report a summary table of all staged sources. Flag any data quality issues.

### Step 6: Merge

Call `merge_sources` MCP tool. Deduplication uses coordinate proximity with tiered bands:
- Within threshold (default 500m): always merge
- 500m--1500m: merge if surface area within 15% (same reservoir, different source coordinates)
- 1500m--8000m: merge if surface area within 15% (large reservoir with centroid vs wall coordinates)

Name-based deduplication is NOT done automatically -- the agent handles that during the visual review step where it can reason about name similarity with context.

Report:
- Total records merged: X from Y sources
- Unique water bodies after deduplication: Z
- Proximity threshold used: Xm
- Dams with coord_spread warnings: N

### Step 7: Name from OSM

Call `enrich_names` MCP tool. This does a single batch OpenStreetMap query to find canonical names for all water bodies by matching coordinates to named water features. This is the source of truth for names -- database names go to alt_names.

Report: "Named X/Y from OSM. Z still unnamed."

### Step 8: Edge Cases and Geocoding

If there are edge cases (records without coordinates that couldn't be merged):

Present them to the user with name, source, height, capacity. For the significant ones (capacity above screening threshold):
- Can you identify which existing water body this matches? (by name similarity, capacity, river)
- If yes, update the matching dam's attributes in the active data file (add height, capacity from the edge case)
- If no match found but the dam seems real, use `enrich_coordinates` MCP tool to attempt geocoding via OSM name search and Nominatim. If coordinates are found, add the dam to the registry.

For small dams below the screening threshold, skip -- they won't affect pair screening.

### Step 9: Enrich

Call `enrich_elevation` MCP tool to add SRTM 30m elevation data. Report coverage.

Call `enrich_grid_distance` MCP tool to add nearest power substation distance. Report coverage.

### Step 10: Overview Map and Visual Review

Assign each dam a structured ID (`{country_code}-{NNN}`, e.g. MAR-001) from `config/parameters.json`. Set initial `status` based on source metadata where available (default to "Operational Dam" if unknown).

Do an automated first pass:
- Classify HydroLAKES-only water bodies with no dam height as `Natural Reservoir`
- Flag known PSH sites as `Existing PSH` (check the data-sources skill for known PSH projects)
- Detect and remove duplicates (dams within proximity threshold that survived merge, same name variants)

Generate the overview map using `generate_overview_map` MCP tool. This creates an interactive map at `data/overview.html` with dams color-coded by status and satellite imagery.

**GATE: Ask the user**: "Automated classification complete: X operational, Y natural reservoirs, Z removed. Want me to visually verify each dam against satellite imagery? This downloads a satellite tile per dam and checks coordinates, structure visibility, and names. It improves data quality but takes time (~1 min per dam, N dams above the screening threshold)."

If the user says yes, do the visual review. If no, skip to the report.

#### Visual Review (satellite imagery)

Load the visual-review skill for the full decision tree, coordinate correction methodology, and verdict codes.

To view a dam, fetch an Esri World Imagery tile:
`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox={lon-0.02},{lat-0.02},{lon+0.02},{lat+0.02}&bboxSR=4326&size=800,600&format=png&f=image`

Save the image to a temp file and view it. Follow the decision tree from the visual-review skill:
1. Is the coordinate outside the target country? Remove.
2. Is a dam wall or water body visible? Classify using the decision tree.
3. Check coordinate position -- if floating in open water, fix to dam wall crest.
4. Check for near-duplicates -- same reservoir with two markers.
5. Check name against map labels. Update if wrong.

Prioritize dams with capacity above the screening threshold. For small water bodies from HydroLAKES with no dam height, classify as `natural_reservoir` without visual review.

After review, regenerate the overview map to confirm the updated statuses.

Report:
- Total reviewed: X
- Operational Dam: A
- Under Construction: B
- Natural Reservoir: C
- Existing PSH: D
- Removed: E (with reasons summary)

### Step 11: Output

The final registry has already been saved by the merge and enrichment steps. Report the output path and final stats:

```
Collection complete for [country].
  Output: [path to saved file]
  Overview map: data/overview.html
  Total water bodies: X
  Named from OSM: A (B%)
  With elevation: C (D%)
  With height: E (F%)
  With capacity: G (H%)
  With grid distance: I (J%)
  Reviewed: R (with S removed)

Ready for /screen-dams.
```
