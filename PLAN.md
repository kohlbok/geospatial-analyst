# Clean Energy Bridge: Morocco PSH Screening Agent

## Project Overview

Build a Claude Code agent (delivered as a plugin) that screens all ~285 of Morocco's existing dams for pumped storage hydropower (PSH) potential. The agent finds dam pairs where pumped storage is (a) technically viable and (b) cost-competitive with battery storage.

**Client**: Paul Jacobson, President, Clean Energy Bridge
**Technical contacts**: Soufiane Hajjani, Tayeb Amegroud (both Casablanca)
**Contract**: Signed March 23, 2026. Package 1 at $4,500. Package 2 ($2,000) conditional.
**Timeline**: Deliver by end of March 2026 (target: March 28-30)
**Deliverables**: Claude Code plugin + Excel workbook + interactive maps

---

## What We Promised (from email thread + proposal)

1. Unified dam registry (editable input file CEB controls, can add/remove dams)
2. Include planned/under-construction dams alongside existing ones
3. Full source code, no lock-in, fully editable by CEB
4. Excel workbook: dam registry, viable pairs, sensitivity analysis, configurable assumptions
5. Interactive maps and terrain profiles for top sites
6. Reusable Claude plugin for other geographies (Thailand, Indonesia)
7. Three QC checkpoints with Tayeb (~30 min each)
8. Configurable constraints: flex any assumption and rerun instantly

---

## Architecture: The Geospatial Analysis Agent

This is not a static script. It is a Claude Code plugin that acts as a **geospatial analysis employee**. The agent reasons through dam combinations, eliminates obvious non-starters fast, spends time on borderline cases, and produces ranked recommendations with full transparency on why each pair was included or excluded.

### Plugin Structure

```
clean-energy-bridge/
├── CLAUDE.md                    Project-level instructions for the agent
├── config/
│   ├── parameters.json          All configurable constraints (head, distance ratio, capacity, etc.)
│   └── scoring_weights.json     Composite scoring weight distributions
├── data/
│   ├── raw/                     Downloaded source databases (gitignored, fetched by agent)
│   ├── processed/               Cleaned, merged, enriched data (JSON)
│   └── geospatial/              SRTM tiles, shapefiles, rasters
├── src/
│   ├── ingestion/
│   │   ├── download.py          Fetch HydroLAKES, GRanD, GDAT, FAO AQUASTAT
│   │   ├── merge.py             Fuzzy-match, deduplicate, build unified registry
│   │   └── elevate.py           SRTM elevation enrichment (wall, centroid, pour point)
│   ├── screening/
│   │   ├── pairs.py             Generate all ~40K dam pairs
│   │   ├── filters.py           Hard constraint filtering (head, distance, capacity, protected areas)
│   │   └── eliminator.py        Fast elimination logic for obvious non-starters
│   ├── terrain/
│   │   ├── profiles.py          Full elevation profile between dam pairs (30m sampling)
│   │   ├── obstacles.py         Ridge detection, river crossings, urban areas, tunnel length
│   │   └── route.py             Optimal penstock/tunnel route analysis
│   ├── scoring/
│   │   ├── energy.py            Energy potential calculation (head x volume x efficiency)
│   │   ├── cost.py              PSH $/MWh vs battery $/MWh benchmark comparison
│   │   ├── composite.py         Multi-criteria composite scoring
│   │   └── sensitivity.py       Sensitivity analysis across parameter ranges
│   └── visualization/
│       ├── maps.py              Interactive folium maps with color-coded pairs
│       ├── terrain_viz.py       Elevation profile charts for top pairs
│       └── export.py            Excel workbook generation, JSON/CSV export
├── output/
│   ├── maps/                    Generated HTML maps
│   ├── reports/                 Terrain profiles, pair analysis reports
│   └── exports/                 Excel workbooks, JSON ranked lists
├── tests/
│   ├── test_merge.py            Validate dam registry against known dams
│   ├── test_filters.py          Constraint filtering unit tests
│   └── test_scoring.py          Scoring calculation verification
└── docs/
    └── methodology.md           Technical methodology reference
```

---

## Phase 1: Data Ingestion and Unified Dam Registry (Days 1-2)

### Step 1.1: Database Download and Parsing

The agent searches for and downloads four public dam databases:

| Database | What it provides | Format | Morocco coverage |
|----------|-----------------|--------|-----------------|
| **HydroLAKES** | Coordinates, surface area, volume, elevation, shoreline | Shapefile | 1.4M+ lakes globally, good Morocco coverage |
| **GRanD v1.3** | Dam height, capacity, year built, purpose, owner | Shapefile | 7,000+ dams globally |
| **GDAT** | Cross-validated coordinates, catchment areas | CSV/Shapefile | 35,000+ dams, highest coordinate accuracy |
| **FAO AQUASTAT** | Purpose categorization, strong North Africa data | Excel | Strong Morocco coverage |

The agent:
1. Downloads each database (or reads from `data/raw/` if already cached)
2. Filters to Morocco (bounding box: lat 27-36, lon -13 to -1)
3. Parses into a standardized schema per source

### Step 1.2: Fuzzy Matching and Deduplication

This is the hardest part of the entire project. Dam names appear in Arabic, French, and English across four databases with inconsistent transliteration.

**Strategy:**
- Primary match key: coordinate proximity (500m threshold using Haversine)
- Secondary: fuzzy name matching (Levenshtein distance, normalized)
- Tertiary: capacity/height cross-validation
- Output: unified registry with unique IDs, provenance tracking (which databases contributed each field)

**Target**: ~285 dams matching Morocco's official count (149 large + 136 small)
**Validation**: Spot-check 10 known dams against Tayeb's manual list

### Step 1.3: Elevation Enrichment

For each dam in the registry:
1. Download NASA SRTM 30m tiles covering Morocco
2. Extract elevation at three points per dam: wall, centroid, pour point
3. Cross-validate against HydroLAKES/EarthEnv-DEM90 embedded elevations
4. Flag discrepancies >20m for manual review

**Output**: `data/processed/dam_registry.json`

```json
{
  "dams": [
    {
      "id": "MAR-001",
      "name": "Al Wahda",
      "names_alt": ["Al Wahda", "Barrage Al Wahda"],
      "sources": ["hydrolakes", "grand", "gdat", "fao"],
      "lat": 34.567,
      "lon": -5.432,
      "elevation_wall_m": 234,
      "elevation_centroid_m": 228,
      "elevation_pour_m": 220,
      "elevation_source": "srtm30",
      "elevation_crosscheck_delta_m": 3,
      "height_m": 88,
      "capacity_mcm": 3730,
      "surface_area_km2": 48.6,
      "year_built": 1996,
      "purpose": ["irrigation", "hydropower", "flood_control"],
      "status": "operational",
      "owner": "ONEE",
      "dam_age_years": 30
    }
  ]
}
```

### QC Checkpoint 1: Dam registry review with Tayeb
- Share registry with Tayeb
- Validate count, identify missing or miscategorized dams
- Confirm planned/under-construction dams are included

---

## Phase 2: Pair Generation and Smart Filtering (Days 2-3)

### Step 2.1: Generate All Possible Pairs

~285 dams = ~40,000 possible pairs (n*(n-1)/2). Each pair is evaluated as a potential PSH configuration where one dam is the upper reservoir and the other is the lower reservoir. Since a pair (A,B) can work in both directions (A upper/B lower, or B upper/A lower), we evaluate both orientations.

### Step 2.2: Fast Elimination (Tier 1 Filters)

These are computationally cheap checks that eliminate the vast majority of pairs instantly:

| Filter | Threshold | Expected elimination |
|--------|-----------|---------------------|
| **Minimum head** | >= 100m elevation difference | ~70% of pairs eliminated |
| **Maximum distance-to-head ratio** | <= 10x (per Tayeb) | ~15% more eliminated |
| **Minimum reservoir capacity** | >= 1M m3 per dam | ~5% more eliminated |

After Tier 1: expect ~500-2,000 surviving pairs.

### Step 2.3: Deeper Filtering (Tier 2 Filters)

These require more computation or external data lookups:

| Filter | Method | Data source |
|--------|--------|-------------|
| **Protected area exclusion** | Spatial join against WDPA polygons | World Database on Protected Areas |
| **Reservoir fill rate** | Exclude dams below 5-10% average fill | Moroccan government daily capacity data (Soufiane's link) |
| **Grid proximity scoring** | Distance to nearest HV substation | OpenStreetMap power grid data |

After Tier 2: expect ~50-200 surviving pairs.

### Step 2.4: Claude Reasoning Layer

This is what makes this an agent, not a script. For borderline cases (pairs that barely pass or barely fail filters), Claude:
1. Examines the specific characteristics of each dam in the pair
2. Considers context (is one dam a major irrigation asset with competing water demands?)
3. Flags pairs that technically pass but have practical concerns
4. Identifies pairs that technically fail by a small margin but warrant a closer look
5. Writes a brief rationale for each decision

**Output**: `data/processed/filtered_pairs.json` with pass/fail/borderline status and rationale per pair.

### QC Checkpoint 2: Pair filtering review with Tayeb
- Share filtered pairs with Tayeb
- Gut-check what made the cut and what didn't
- Adjust thresholds if needed based on domain expertise

---

## Phase 3: Terrain Analysis (Days 3-4)

For each viable pair (~50-200):

### Step 3.1: Elevation Profile Extraction

- Sample SRTM elevation every 30m along the straight-line path between dam walls
- Identify the maximum ridge height along the path
- Calculate effective tunnel length (distance through terrain above the lower dam's elevation)

### Step 3.2: Obstacle Identification

Using OpenStreetMap data, identify along each pair's route:
- **Rivers and river crossings**: number and width
- **Urban areas**: settlements in the path
- **Roads and infrastructure**: major roads, railways
- **Tunnels >5km**: flag as high-cost concern

### Step 3.3: Route Feasibility Assessment

For each pair, the agent determines:
- Is a direct penstock route feasible, or would tunneling be required?
- Estimated tunnel length (if terrain exceeds direct route)
- Terrain difficulty classification: easy / moderate / challenging / infeasible

Pairs that fail terrain viability (e.g., require >10km tunnel through mountain, cross through city center) are excluded before cost comparison.

**Output**: `output/reports/` terrain profile charts (PNG/HTML) per viable pair.

---

## Phase 4: Energy and Cost Analysis (Days 4-5)

### Step 4.1: Energy Potential Calculation

For each terrain-viable pair:

```
Energy (MWh) = head (m) x volume (m3) x water_density (1000 kg/m3) x gravity (9.81 m/s2) x efficiency (0.75-0.80) / 3,600,000
```

Run at three reservoir levels:
- **Conservative**: minimum historical fill level (from 10-year data)
- **Standard**: average fill level
- **Optimistic**: maximum fill level

### Step 4.2: Cost Competitiveness vs Battery Storage

For Package 1 (existing dam pairs), this is a benchmark comparison:

- **PSH benchmark**: standard $/MWh for pumped hydro (informed by Tayeb's Morocco knowledge, typically $150-250/MWh installed)
- **Battery benchmark**: ~$100,000/MWh (from Tayeb's call)
- **Comparison**: PSH $/MWh vs battery $/MWh for equivalent storage capacity

No construction cost modeling in Package 1 because the dams already exist. The cost comparison focuses on conversion/retrofit costs vs battery installation.

### Step 4.3: Composite Scoring

Each pair receives a composite score across multiple dimensions:

| Dimension | Weight (default) | What it measures |
|-----------|-----------------|------------------|
| Cost competitiveness | 30% | PSH $/MWh vs battery benchmark |
| Energy potential | 25% | Total storable energy at standard fill |
| Grid proximity | 20% | Distance to nearest HV substation |
| Reservoir suitability | 15% | Fill rate stability, capacity, dam condition |
| Regulatory risk | 10% | Protected areas nearby, competing water uses |

Three weight distributions run by default (cost-weighted, balanced, energy-weighted) for sensitivity.

**Output**: Ranked list of all viable pairs with scores, energy output, and cost comparison.

---

## Phase 5: Output and Visualization (Days 5-6)

### Step 5.1: Interactive Maps (Folium)

- **Full Morocco map**: all 285 dams plotted, color-coded by viability status
  - Green: viable pair member
  - Yellow: borderline
  - Red: no viable pairs
  - Blue: planned/under-construction
- **Pair connection lines**: colored by composite score (green = top tier, orange = mid, red = low)
- **Click-through**: each dam shows popup with registry data, each pair line shows energy potential and score
- **Top 10 pairs map**: dedicated map zoomed to the best candidates

### Step 5.2: Terrain Profile Charts

For the top 10-20 pairs:
- Full elevation profile between dams
- Annotated with obstacles (rivers, urban areas, ridges)
- Head height clearly marked
- Tunnel sections highlighted

### Step 5.3: Excel Workbook

Tab structure:
1. **Dam Registry**: all ~285 dams with full attributes
2. **All Pairs**: every pair evaluated, with pass/fail status and filter that eliminated it
3. **Viable Pairs (Ranked)**: ranked by composite score, with energy output and cost comparison
4. **Top 10 Deep Dive**: detailed analysis per top pair
5. **Sensitivity Analysis**: results under tight/standard/relaxed thresholds
6. **Configuration**: all parameters used, so CEB can see exactly what assumptions drove results

### Step 5.4: JSON Export

```json
{
  "metadata": {
    "run_date": "2026-03-28",
    "parameters": { ... },
    "total_dams": 285,
    "pairs_evaluated": 40470,
    "pairs_viable": 87,
    "top_10_pairs": [ ... ]
  },
  "ranked_pairs": [
    {
      "rank": 1,
      "upper_dam": "MAR-042",
      "lower_dam": "MAR-118",
      "head_m": 312,
      "distance_km": 2.8,
      "distance_head_ratio": 8.97,
      "energy_mwh_standard": 1247,
      "energy_mwh_conservative": 892,
      "psh_cost_per_mwh": 187,
      "battery_cost_per_mwh": 285,
      "cost_advantage_pct": 34.4,
      "composite_score": 0.87,
      "grid_distance_km": 4.2,
      "terrain_difficulty": "moderate",
      "tunnel_length_km": 1.2,
      "obstacles": ["1 river crossing"],
      "rationale": "Strong head with short distance. Both dams operational with stable fill rates above 40% over past 10 years. Single river crossing manageable. 4.2km to nearest 225kV substation."
    }
  ]
}
```

---

## Phase 6: Testing and QC (Days 6-7)

### Validation Strategy

1. **Registry validation**: compare against Tayeb's manual list of ~15 known locations
2. **Filter validation**: manually verify 5 pairs that passed and 5 that failed each filter
3. **Energy calculation validation**: cross-check 3 pairs against manual calculation
4. **End-to-end test**: full pipeline run, verify no data loss between stages
5. **Edge cases**: dams with missing data, pairs at exact threshold boundaries

### QC Checkpoint 3: Pre-delivery review with Tayeb
- Walk through top 10 pairs
- Compare against his manual analysis of ~15 locations
- Validate scoring makes domain sense
- Confirm if Package 2 is needed based on shortlist quality

---

## Configuration: parameters.json

```json
{
  "screening": {
    "min_head_m": 100,
    "max_distance_head_ratio": 10,
    "min_reservoir_capacity_mcm": 1,
    "min_fill_rate_pct": 10,
    "ideal_fill_rate_pct": 40,
    "max_tunnel_length_km": 10,
    "protected_area_buffer_km": 1
  },
  "energy": {
    "round_trip_efficiency": 0.78,
    "water_density_kg_m3": 1000,
    "gravity_m_s2": 9.81
  },
  "cost": {
    "battery_benchmark_usd_per_mwh": 100000,
    "psh_benchmark_usd_per_mwh_low": 150,
    "psh_benchmark_usd_per_mwh_high": 250,
    "depreciation_years": 30
  },
  "scoring": {
    "weights": {
      "cost_competitiveness": 0.30,
      "energy_potential": 0.25,
      "grid_proximity": 0.20,
      "reservoir_suitability": 0.15,
      "regulatory_risk": 0.10
    }
  },
  "output": {
    "top_n_detailed": 10,
    "top_n_terrain_profiles": 20,
    "sensitivity_runs": ["tight", "standard", "relaxed"]
  },
  "morocco_bbox": {
    "lat_min": 27.0,
    "lat_max": 36.0,
    "lon_min": -13.0,
    "lon_max": -1.0
  }
}
```

CEB can edit this file and rerun. Every parameter the agent uses comes from here.

---

## Geospatial Visualization: The "Google Earth" Layer

This is what makes the deliverable feel like a geospatial analysis employee, not a spreadsheet:

1. **Interactive Folium maps** (HTML files, open in any browser):
   - Full dam registry map with clustering at zoom levels
   - Viable pair connections with color-coded scoring
   - Terrain profile overlays
   - Grid infrastructure (substations, transmission lines from OSM)

2. **KML/KMZ export** for Google Earth:
   - All dams as placemarks with full attributes
   - Pair connections as line features
   - Terrain profile paths
   - Color coding matching the analysis scoring

3. **GeoJSON export** for GIS tools:
   - Dam points with all registry attributes
   - Pair connection lines with screening results
   - Usable in QGIS, ArcGIS, or any GIS platform

The agent generates all three formats automatically. Paul/Soufiane/Tayeb can open the HTML maps in a browser, load KMZ files in Google Earth, or import GeoJSON into professional GIS tools.

---

## What Makes This an Agent (Not a Script)

1. **Database search**: the agent searches for and identifies relevant databases, handles download failures, tries alternative sources
2. **Intelligent parsing**: handles inconsistent formats, Arabic/French/English naming, missing fields
3. **Reasoning on borderline cases**: Claude evaluates pairs that are near filter thresholds, writes rationales
4. **Configurable re-runs**: change any parameter in parameters.json, rerun the command, get new results
5. **Natural language interaction**: CEB team can ask the agent questions about results, request adjustments, explore "what if" scenarios
6. **Self-documenting**: every decision the agent makes is logged with reasoning

---

## Execution Order for the Builder

The person building this (agent in the CEB folder) should execute in this order:

### Day 1: Foundation
- [ ] Set up Python environment (GeoPandas, rasterio, folium, shapely, scipy, openpyxl)
- [ ] Write `config/parameters.json` with all defaults
- [ ] Build `src/ingestion/download.py`: fetch all four databases, cache in `data/raw/`
- [ ] Build `src/ingestion/merge.py`: parse each database, fuzzy match, deduplicate
- [ ] Test: verify dam count is in the ~250-300 range for Morocco

### Day 2: Elevation + Registry Completion
- [ ] Build `src/ingestion/elevate.py`: SRTM tile download, elevation extraction
- [ ] Cross-validate elevations against embedded database values
- [ ] Generate `data/processed/dam_registry.json`
- [ ] Build basic registry visualization (folium map of all dams)
- [ ] **QC Checkpoint 1 material ready**

### Day 3: Pair Screening
- [ ] Build `src/screening/pairs.py`: generate all pair combinations with both orientations
- [ ] Build `src/screening/filters.py`: implement Tier 1 (head, distance ratio, capacity) and Tier 2 (protected areas, fill rate, grid proximity) filters
- [ ] Build `src/screening/eliminator.py`: fast elimination with logging
- [ ] Generate `data/processed/filtered_pairs.json`
- [ ] **QC Checkpoint 2 material ready**

### Day 4: Terrain Analysis
- [ ] Build `src/terrain/profiles.py`: elevation profile extraction between dam pairs
- [ ] Build `src/terrain/obstacles.py`: OSM data overlay for obstacle identification
- [ ] Build `src/terrain/route.py`: tunnel length estimation, terrain difficulty classification
- [ ] Generate terrain profiles for top 50 pairs

### Day 5: Scoring and Output
- [ ] Build `src/scoring/energy.py`: energy potential at three fill levels
- [ ] Build `src/scoring/cost.py`: PSH vs battery benchmark comparison
- [ ] Build `src/scoring/composite.py`: multi-criteria scoring with configurable weights
- [ ] Build `src/scoring/sensitivity.py`: tight/standard/relaxed threshold runs
- [ ] Build `src/visualization/maps.py`: interactive folium maps
- [ ] Build `src/visualization/terrain_viz.py`: elevation profile charts
- [ ] Build `src/visualization/export.py`: Excel workbook + JSON + KML/GeoJSON

### Day 6: Testing and Polish
- [ ] Run full end-to-end pipeline
- [ ] Validate against Tayeb's manual analysis
- [ ] Fix edge cases, missing data handling
- [ ] Generate final outputs
- [ ] **QC Checkpoint 3 material ready**

### Day 7: Delivery
- [ ] Package as Claude Code plugin with CLAUDE.md
- [ ] Write user-facing documentation
- [ ] Prepare delivery walkthrough for Tayeb and Paul

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Dam name matching across languages | HIGH | MEDIUM | Coordinate proximity as primary key, not names |
| SRTM gaps in mountainous areas | LOW | LOW | Full Morocco coverage confirmed, fill with EarthEnv-DEM90 |
| Moroccan dam capacity website not machine-readable | MEDIUM | LOW | Not a blocker for screening, only affects fill rate scoring |
| Fewer viable pairs than expected | MEDIUM | LOW | This is actually useful information for CEB; triggers Package 2 discussion |
| Data download failures | LOW | LOW | Agent retries, falls back to cached data, alerts user |

---

## Follow-on Work (Not in Scope, But on the Table)

| Opportunity | Est. price | Trigger |
|------------|-----------|---------|
| Package 2: New dam site scanning | $2,000 | If Package 1 shortlist is thin |
| Country expansion (Thailand/Indonesia) | $2,000-3,000/country | After Morocco proves the tool |
| Financial modeling tool (Asia) | $4,000-6,000 | Paul loses Morocco contractor |
| R&I capability | $2,000-4,000 retainer | After trust established |

---

## Key Contacts

- **Paul Jacobson** (President, DC): pjacobson@cleanenergybridge.org, +1-202-378-7995
- **Soufiane Hajjani** (Casablanca): shajjani@cleanenergybridge.org
- **Tayeb Amegroud** (Casablanca): tamegroud@gmail.com

## Items Pending from CEB

- [ ] Soufiane: daily dam capacity website link (10-year historical fill data)
- [ ] Tayeb: prior report templates and output formats
- [ ] Tayeb: PSH benchmark data for Morocco (cost per MWh)
- [ ] Tayeb: updated CapEx construction cost data (for Package 2)
