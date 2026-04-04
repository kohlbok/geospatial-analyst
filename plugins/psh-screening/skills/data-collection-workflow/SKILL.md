# Data Collection Workflow

## Overview

This skill teaches how to collect, inspect, and merge dam data for any country using the generic MCP tools. The agent drives the entire process -- figuring out column mappings, data quality, and reviewing merge results.

## Unified Dam Schema

Every source gets mapped to this schema before staging:

| Field | Type | Unit | Required |
|-------|------|------|----------|
| name | string | - | yes |
| lat | float | decimal degrees (WGS84) | preferred |
| lon | float | decimal degrees (WGS84) | preferred |
| height_m | float | meters | preferred |
| capacity_mcm | float | million cubic meters | preferred |
| surface_area_km2 | float | square kilometers | no |
| year_built | int | year | no |
| river | string | - | no |
| basin | string | - | no |
| purpose | list[string] | - | no |
| elevation_m | float | meters above sea level | no |
| source | string | source identifier | auto |
| id | string | {country_code}-{NNN} | auto |
| status | string | dam classification | no |
| raw_name | string | original name before corrections | no |
| source_count | int | number of sources contributing | auto |
| coord_confidence | string | exact/approximate/estimated | no |
| capacity_source | string | origin of capacity value | no |
| needs_review | string | free-text review notes | no |

## ID Assignment

After merging, assign each dam a structured ID: `{country_code}-{NNN}` (e.g. MAR-001, MAR-002). The country code comes from `config/parameters.json`. IDs are sequential, starting at 001. This makes dams easy to reference during review and in reports.

## Visual Review Fields

These fields are set during the visual review step (after enrichment, before final output). They are optional but significantly improve data quality.

### Status

Classification of the dam/water body. Drives the overview map color coding and determines what enters screening.

| Value | Meaning | Enters screening? |
|-------|---------|-------------------|
| Operational Dam | Confirmed existing dam | Yes |
| Under Construction | Dam being built, not yet operational | Yes |
| Natural Reservoir | Water body without a dam wall (lake, lagoon) | Yes (may be viable as-is) |
| Existing PSH | Already operating as pumped storage | No (already developed) |
| Removed | False positive, duplicate, or wrong country | No |

### Coordinate Confidence

Set during visual review by checking the dam against satellite imagery:
- **exact**: Dam structure clearly visible at the coordinates
- **approximate**: Structure visible but coordinates are slightly off (within ~500m)
- **estimated**: No structure visible, location from textual description or coarse source only

### needs_review

Free-text notes field for flagging issues. Common patterns:
- `coord_spread:XXXm` -- sources disagree on location by XXX meters
- `possible_duplicate_of_{ID}` -- may be the same dam as another record
- `capacity:X-YMCM` -- capacity uncertain, range estimate
- `coord_fixed_from_visual_review` -- coordinates were corrected based on satellite imagery
- `name_conflict` -- sources give different names

### Removed Dams

Dams with `status: Removed` stay in the dataset but are excluded from screening. The `needs_review` field records the removal reason (e.g. "duplicate of MAR-009", "fishpond not dam", "coordinates in ocean", "wrong country"). Keeping removed dams prevents re-adding them in future collection runs.

## Step-by-Step Workflow

### Step 1: Set Up Country

Read `config/parameters.json` to get the country config (bbox, country name). If the country isn't configured yet, add it.

### Step 2: Collect Global Sources

These sources cover most countries. Process each one:

**FAO AQUASTAT** (best for names, height, capacity, purpose)
1. Call `download_file` with the country's FAO URL
2. Call `inspect_file` to see the Excel structure (header row, column names)
3. Determine column mapping by reading the sample rows
4. Call `parse_tabular` with the mapping and country/bbox filter

**GeoDAR + GRanD** (best for coordinates, cross-validated)
1. Call `download_file` for GeoDAR from Zenodo
2. Call `inspect_file` on the GeoDAR v11 CSV
3. Call `parse_tabular` with bbox filter and column mapping
4. Also inspect `GRanD_v13_issues.csv` in the same package -- it has full GRanD data
5. Filter GRanD to the target country, parse and stage

**HydroLAKES** (best for reservoir volumes, areas, geometry)
1. Call `download_file` for HydroLAKES shapefile
2. Call `inspect_file` to see columns
3. Call `parse_tabular` with bbox filter and type filter (Lake_type in [1,2,3] for reservoirs)

### Step 3: Find Country-Specific Sources

Use web search to find additional sources. Common places to look:
- Wikipedia list of dams (search in the country's primary language)
- Government water ministry / dam authority websites
- ArcGIS/GIS portal data layers
- National open data portals

For each source found:
1. Download using `download_file` or fetch with WebFetch
2. Inspect structure with `inspect_file`
3. Reason about column mapping (names may be in local language)
4. Parse and stage

### Step 4: Review Staged Sources

Review coverage statistics across all staged sources:
- How many records per source?
- What percentage have coordinates?
- What percentage have height and capacity?
- Are there obvious gaps?

Report findings to the user before merging.

### Step 5: Merge

Call `merge_sources`. This uses proximity-based deduplication:
- Records within the configured proximity threshold (default 500m) are treated as the same dam
- Merged dams get the best name, averaged coordinates, max height/capacity
- Records without coordinates become edge cases for agent review

### Step 6: Review Edge Cases

For records without coordinates that couldn't be merged automatically:
- The agent reviews each one by name, capacity, height, river
- Determines if it matches an existing dam (agent judgment, not fuzzy matching)
- If matched, update the dam record directly
- If unmatched and the dam seems real, note it as missing coordinates

### Step 7: Enrich with Elevation

Call `enrich_elevation` to add SRTM 30m elevation data to all dams with coordinates.

## Column Mapping Cheat Sheet

Common column names across databases:

| Unified Field | Common Source Names |
|---|---|
| name | DAM_NAME, Dam_name, dam_name, Name, name, Lake_name, Nom |
| lat | LAT_DD, Latitude, latitude, lat, LAT, Lat, Y |
| lon | LONG_DD, Longitude, longitude, lon, LON, Lng, X |
| height_m | DAM_HGT_M, Dam_hgt, dam_height, Height, height, Hauteur |
| capacity_mcm | CAP_MCM, Cap_mcm, capacity, Storage, Vol_total, Capacite |
| surface_area_km2 | AREA_SKM, Area_skm, Lake_area, surface_area, Superficie |
| year_built | YEAR, Year, year_built, Completion, Annee |

## Unit Conversions

- HydroLAKES Vol_total: already in MCM (million cubic meters)
- If capacity is in cubic meters: divide by 1,000,000
- If capacity is in acre-feet: multiply by 0.001233
- If area is in hectares: divide by 100
- If area is in square meters: divide by 1,000,000

## Quality Validation

After merging, check:
- Total dam count vs expected (from official statistics)
- Coordinate coverage percentage
- Height and capacity coverage for dams > 10 MCM
- All major known dams present (spot-check top 10 by capacity)
