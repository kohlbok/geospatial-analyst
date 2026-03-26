# Data Sources

## Dam Databases

### HydroLAKES (hydrosheds.org)
- 1.4M+ lakes/reservoirs globally
- Fields: coordinates, surface area, volume, elevation, shoreline length
- Format: shapefile
- Good Morocco coverage
- Free download

### GRanD v1.3 (globaldamwatch.org)
- 7,000+ dams globally
- Fields: dam height, capacity, year built, purpose, owner
- Format: shapefile
- Linked to HydroLAKES polygons
- Free download

### GDAT (zenodo.org/record/6163413)
- 35,000+ dams globally
- Fields: cross-validated coordinates, catchment areas
- Highest coordinate accuracy of all databases
- Format: CSV/shapefile
- Free download

### FAO AQUASTAT (fao.org/aquastat)
- 14,000+ dams
- Fields: purpose categorization, region
- Format: Excel files by region
- Strong North Africa coverage
- Free download

## Elevation Data

### NASA SRTM 30m
- Full Morocco coverage
- 30m resolution digital elevation model
- Free from USGS EarthExplorer
- Works with rasterio in Python
- GeoTIFF format

### EarthEnv-DEM90
- 90m resolution
- Integrated into HydroLAKES for lake elevation estimates
- Used as cross-check against SRTM

## Supporting Data

### OpenStreetMap
- Power grid lines and substations (fairly current for Morocco)
- Urban areas and settlements
- Roads and railways
- Overpass API or direct download

### WDPA (World Database on Protected Areas)
- Protected area boundaries for exclusion filtering
- protectedplanet.net
- Shapefile format

### Global Human Settlement Layer
- Settlement/urban data for route analysis

## Morocco-Specific

### Official Dam Count
149 large + 136 small = 285 total

### Existing PSH Facilities
- Afourar PETS: 464 MW, operational since 2004
- Abdelmoumen: 350 MW, under construction
- El Menzel: 300-400 MW, target 2028

### Dam Capacity Data
Soufiane (CEB) to share a Moroccan government website with daily capacity data for each major dam over the past 10 years. If not yet available, proceed without fill rate filtering and add it later.

## Python Libraries

- **GeoPandas**: core geospatial data handling, spatial joins, distance calculations
- **rasterio**: SRTM raster data reading and elevation extraction
- **shapely**: geometry operations for pair distance and route analysis
- **folium**: interactive map generation
- **scipy**: distance calculations (Haversine/Vincenty)
- **fiona**: shapefile reading
- **pyproj**: coordinate transformations
- **openpyxl**: Excel workbook generation
- **simplekml**: KML/KMZ export
