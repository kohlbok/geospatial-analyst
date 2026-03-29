# PSH Screening Methodology

## Overview

Screen all existing dams in a country for pumped storage hydropower (PSH) potential. Find dam pairs where the elevation difference, distance, and reservoir capacity make pumped storage technically viable and cost-competitive with battery storage.

## Scoring Formula

Each viable pair gets a composite score from 0 to 1. Higher is better.

```
composite_score = W1 * energy_score + W2 * cost_score + W3 * grid_score + W4 * reservoir_score
```

Default weights: W1=0.35, W2=0.30, W3=0.20, W4=0.15. Configurable in parameters.json.

Each sub-score is normalized 0-1 across all viable pairs (best pair gets 1, worst gets 0).

### 1. Energy Potential Score (weight: 0.35)

Raw value:
```
energy_mwh = head_m * usable_volume_m3 * water_density * gravity * efficiency / 3,600,000,000

where:
  head_m          = elevation difference between upper and lower dam (meters)
  usable_volume   = min(upper_capacity, lower_capacity) * fill_fraction (m3)
  fill_fraction   = 0.60 (standard), 0.30 (conservative), 0.90 (optimistic)
  water_density   = 1000 kg/m3
  gravity         = 9.81 m/s2
  efficiency      = 0.78 (round-trip, from config)
```

Normalized: energy_score = (pair_energy - min_energy) / (max_energy - min_energy)

Higher energy = better score. Driven primarily by head and reservoir size.

### 2. Cost Advantage Score (weight: 0.30)

Raw value:
```
psh_cost_usd_per_mwh:
  if head > 300m:  $150/MWh (low end)
  if head > 200m:  $200/MWh (midpoint)
  else:            $250/MWh (high end)

  + 5% penalty per km of tunnel beyond 3km
  + 1% penalty per km of distance beyond 20km

cost_advantage_pct = (battery_cost - psh_cost) / battery_cost * 100

where:
  battery_cost = $300/MWh (from config, confirm with client for target country)
```

Normalized: cost_score = (pair_advantage - min_advantage) / (max_advantage - min_advantage)

Higher cost advantage = better score. High-head pairs strongly favored.

### 3. Grid Proximity Score (weight: 0.20)

Raw value:
```
grid_distance_km = distance from nearest dam in the pair to nearest HV substation (>=60kV)

Looked up from OpenStreetMap Overpass API, cached in dams.json.
For a pair, grid_distance = min(upper_dam_grid_distance, lower_dam_grid_distance)
```

Normalized: grid_score = 1 - (pair_distance - min_distance) / (max_distance - min_distance)

Closer to grid = better score. A pair 2km from a 225kV substation scores much better than one 50km away.

### 4. Reservoir Quality Score (weight: 0.15)

Raw value:
```
reservoir_score = normalized(min_capacity_of_pair)
```

Normalized across all pairs. Larger minimum capacity = better score.

A pair is only as good as its smaller reservoir (you can only pump as much water as the smaller one holds).

## Screening Filters

Before scoring, pairs must pass these hard cutoffs:

```
head_m >= min_head_m (default: 100m)
distance_km <= max_distance_km (default: 30km)
both dams capacity_mcm >= min_capacity_mcm (default: 1 MCM)
```

Pairs that fail are not eliminated from the output, they just get filtered before scoring. The full pair list with pass/fail status is available in the results.

## Process

1. Load dam registry from data/dams.json
2. Generate all n*(n-1)/2 pair combinations (brute force)
3. Apply screening filters
4. Calculate energy, cost, grid, reservoir scores for viable pairs
5. Compute weighted composite score
6. Rank by composite score
7. Generate outputs (Excel, map, KML, GeoJSON)
