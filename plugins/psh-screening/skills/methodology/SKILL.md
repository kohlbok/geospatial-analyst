# PSH Screening Methodology

## Overview

This methodology follows NREL's established Pumped Storage Hydropower supply curve approach. Screen all existing dams in a country for PSH potential by: (1) building a unified dam registry from multiple databases, (2) generating all possible dam pairs, (3) filtering through engineering constraints, (4) analyzing terrain between viable pairs, (5) scoring on energy potential and cost competitiveness, (6) producing ranked output with maps.

## The Two Questions

Every pair must answer:
1. **Viability**: is this site technically doable? (elevation, distance, terrain, capacity)
2. **Cost competitiveness**: is PSH cheaper than battery storage for equivalent capacity?

## Six-Step Process

### Step 1: Dam Registry Collection
Collect dam data from all available public sources. Build a unified registry with unique IDs, coordinates, elevation, capacity, height, purpose, and status for every dam in the target country. Primary merge key is coordinate proximity (500m), not name matching (names vary across Arabic/French/English).

### Step 2: Elevation Enrichment
Extract elevation at three points per dam using NASA SRTM 30m: dam wall, reservoir centroid, pour point. Cross-validate against database-embedded elevations. Flag discrepancies >20m.

### Step 3: Pair Generation and Fast Filtering
Generate all n*(n-1)/2 possible pairs. Each pair evaluated in both orientations (A upper/B lower, B upper/A lower). Apply hard engineering constraints to eliminate non-starters fast:
- Minimum head (elevation difference)
- Maximum distance-to-head ratio
- Minimum reservoir capacity
- Protected area exclusion

### Step 4: Terrain and Route Analysis
For surviving pairs, extract full SRTM elevation profile between dam walls (30m sampling). Identify ridges, river crossings, urban areas, tunnel requirements. Classify terrain difficulty.

### Step 5: Scoring and Ranking
Calculate energy potential (head x volume x efficiency). Compare PSH cost against battery benchmark. Composite score across: cost competitiveness, energy potential, grid proximity, reservoir suitability, regulatory risk. Run multiple weight distributions.

### Step 6: Sensitivity Analysis
Rerun screening under tight, standard, and relaxed constraint thresholds. Show how the shortlist changes with different assumptions.

## Key Formulas

### Energy Potential
```
Energy (MWh) = head_m * volume_m3 * water_density * gravity * efficiency / 3,600,000
```
Where: water_density = 1000 kg/m3, gravity = 9.81 m/s2, efficiency = 0.75-0.80

### Distance-to-Head Ratio
```
ratio = horizontal_distance_m / head_m
```
Must be <= threshold (Tayeb specified 10, NREL uses 12).

## Output Requirements

1. Ranked list of top 100 pairs with the best 10 highlighted
2. Interactive maps (Folium HTML)
3. KML/KMZ for Google Earth
4. GeoJSON for GIS tools
5. Excel workbook with all data, assumptions, and sensitivity results
6. JSON export for programmatic use
