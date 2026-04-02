# /collect-dams

Collect dam and water body data for a country from global databases and user-provided sources.

## Skills

Load: data-sources, data-collection-workflow

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

Then ask: "Know any additional sources? Government portals, spreadsheets, URLs?"

### Step 3: Download

Download each source using `download_file` MCP tool. Use the URLs from the data-sources skill. For each:
- Report success/failure immediately
- If a download fails, note it and continue with the others
- If the user provided additional URLs, download those too

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

Call `merge_sources` MCP tool. Deduplication is by coordinate proximity only -- no name matching. Report:
- Total records merged: X from Y sources
- Unique water bodies after deduplication: Z
- Proximity threshold used: Xm

### Step 7: Name from OSM

Call `enrich_names` MCP tool. This does a single batch OpenStreetMap query to find canonical names for all water bodies by matching coordinates to named water features. This is the source of truth for names -- database names go to alt_names.

Report: "Named X/Y from OSM. Z still unnamed."

### Step 8: Edge Cases

If there are edge cases (records without coordinates that couldn't be merged):

Present them to the user with name, source, height, capacity. Review each one:
- Can you identify which existing water body this matches? (by capacity, river)
- If yes, note it as a match (the agent can update dams.json directly)
- If no match found, note it as unmatched

### Step 9: Enrich

Call `enrich_elevation` MCP tool to add SRTM 30m elevation data. Report coverage.

Call `enrich_grid_distance` MCP tool to add nearest power substation distance. Report coverage.

### Step 10: Output

Save the final registry:
- `data/dams.json` (already saved, now fully enriched)
- `data/dams.xlsx` (create Excel version for non-technical users)

Report final stats:
```
Collection complete for [country].
  Total water bodies: X
  Named from OSM: A (B%)
  With elevation: C (D%)
  With height: E (F%)
  With capacity: G (H%)
  With grid distance: I (J%)

Run /screen-dams to start screening.
```
