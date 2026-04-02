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
