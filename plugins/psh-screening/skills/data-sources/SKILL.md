# Data Sources

## Global Dam Databases

These sources work for any country. Use the agent-driven workflow (see data-collection-workflow skill) to download, inspect, map columns, and stage each one.

### FAO AQUASTAT (fao.org/aquastat)
- 14,000+ dams globally, organized by country
- Fields: dam name, coordinates (partial), height, capacity, purpose, river, basin, year
- Format: Excel (.xlsx) per country
- Country-specific download: `https://www.fao.org/nr/water/aquastat/dams/country/{ISO3}-dams_eng.xlsx`
- Africa-wide fallback: `https://storage.googleapis.com/fao-maps-catalog-data/geonetwork/aquamaps/african_dams.xls`
- Best source for dam names and attributes. Often the most complete country-level list.
- Note: many dams lack coordinates. Cross-reference with other sources.

### GeoDAR + GRanD (zenodo.org/records/6163413)
- GeoDAR: 35,000+ dams globally with cross-validated coordinates
- GRanD v1.3 data embedded in `GRanD_v13_issues.csv` inside the GeoDAR package
- GRanD has: dam name, height, capacity, area, year, purpose, coordinates, catchment, elevation
- GeoDAR has: coordinates (highest accuracy), GRanD ID linkage, reservoir volume
- Format: CSV + Shapefile
- Single download: `https://zenodo.org/api/records/6163413/files/GeoDAR_v10_v11.zip/content`
- Key files: `GeoDAR_v11_dams.csv`, `GRanD_v13_issues.csv`

### HydroLAKES (hydrosheds.org)
- 1.4M+ lakes/reservoirs globally
- Fields: coordinates, surface area, volume, elevation, shoreline length, GRanD ID
- Format: shapefile (large, ~4GB global)
- Filter by bbox and Lake_type in [1,2,3] for reservoirs
- Download: `https://data.hydrosheds.org/file/HydroLAKES/HydroLAKES_polys_v10_shp.zip`
- Mostly unnamed but has volumes, areas, and polygon geometry
- Use GRanD ID to link to named dams from GRanD

### ICOLD (icold-cigb.org)
- World Register of Dams: 60,000+ dams globally
- Fields: dam name, height, type, capacity, purpose, year, country
- Access: Requires registration or purchase. Some national ICOLD committees publish subsets freely.
- Format: varies (CSV, PDF tables, web portals)
- Good for filling gaps that FAO AQUASTAT misses, especially smaller dams
- Note: Data may need manual extraction from PDF tables. No standard API.

### GDW / GOODD (Global Dam Watch)
- 38,000+ dam locations with satellite-derived coordinates
- Fields: coordinates, river, catchment area
- Format: CSV/shapefile
- Download: Via globaldamwatch.org or GOODD dataset
- Strengths: Independent coordinate source for cross-validation. Good coverage in Africa and Asia.
- Limitations: Minimal attribute data (no height/capacity). Best used as a coordinate supplement to FAO/GRanD.

## Elevation Data

### NASA SRTM 30m
- Global coverage (60N to 56S latitude)
- 30m resolution digital elevation model
- Tile download: `https://elevation-tiles-prod.s3.amazonaws.com/skadi/{NS}{lat}/{NS}{lat}{EW}{lon}.hgt.gz`
- Handled automatically by the `enrich_elevation` tool

## Supporting Data

### OpenStreetMap
- Power grid lines and substations
- Urban areas and settlements
- Roads and railways
- Overpass API or direct download

### WDPA (World Database on Protected Areas)
- Protected area boundaries for exclusion filtering
- protectedplanet.net

## Country-Specific Sources

### Finding Additional Sources

For any country, search for:
1. **Wikipedia**: "List of dams in {country}" or equivalent in local language (e.g., "Barrages du Maroc" in French)
2. **Government data portals**: water ministry, dam authority, open data portal
3. **ArcGIS feature services**: search `{country} dams site:arcgis.com`
4. **Regional databases**: World Bank, Asian Development Bank, African Development Bank
5. **ICOLD national committees**: Some countries have their own ICOLD member that publishes dam lists freely
6. **Basin water agencies**: National water agencies often publish dam inventories (e.g., Agence de Bassin Hydraulique in Morocco, Basin Water Boards in India). Search for `{country} water agency dam list`.
7. **Under-construction tracking**: Government infrastructure plans, World Bank project databases, news articles about new dam projects

### Morocco (MAR)
- Official count: 149 large + 136 small = 285 total
- FAO AQUASTAT: 152 dams
- GRanD: 39 major dams
- Wikipedia FR "Barrages du Maroc": ~152 dams with height/capacity/year (no coords)
- data.gov.ma: Souss Massa basin dataset
- ArcGIS: Morocco dams feature layer ("Barrages du Maroc")
- ABH (Agence de Bassin Hydraulique) websites: regional basin agencies publish dam fill rates and operational data
- DGH (Direction Generale de l'Hydraulique) tableau: government capacity and fill rate data
- Existing PSH: Afourar PETS (464 MW), Abdelmoumen (350 MW under construction), El Menzel (300-400 MW target 2028)
- Government daily dam capacity data (if available from client)

### Thailand (THA)
- EGAT (Electricity Generating Authority of Thailand) dam database
- Royal Irrigation Department
- Thai Wikipedia dam list

### Indonesia (IDN)
- PLN (state electricity company) hydropower data
- Ministry of Public Works dam registry
- Indonesian Wikipedia dam lists

## MCP Tools for Data Collection

Use these tools in sequence:

1. `download_file(url, filename, subfolder)` -- download any source
2. `inspect_file(path, max_rows)` -- see columns, dtypes, sample data
3. `parse_tabular(path, column_mapping, filters, output_name)` -- parse with agent-defined mapping and stage
4. `fetch_under_construction()` -- stage under-construction dams from WikiData + OSM
5. `merge_sources(proximity_threshold_m, output_name)` -- merge all staged sources (tiered proximity + surface area)
6. `enrich_names()` -- canonical names from OpenStreetMap
7. `enrich_coordinates()` -- geocode dams without coordinates
8. `enrich_elevation()` -- add SRTM 30m elevations
9. `enrich_grid_distance(max_workers)` -- nearest HV substation distance
10. `generate_overview_map()` -- interactive map for visual review
