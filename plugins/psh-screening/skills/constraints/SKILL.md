# Engineering Constraints

Source: Tayeb Amegroud and Soufiane Hajjani (Clean Energy Bridge, Morocco), technical call March 16, 2026.

## Hard Filters (Tier 1, applied first, computationally cheap)

### Head (Elevation Difference)
- Minimum: 100m (configurable, parameters.json)
- This is the vertical distance between upper and lower reservoir water levels
- Higher head = more energy per unit volume

### Distance-to-Head Ratio
- Maximum: 10 (Tayeb's specification)
- NREL methodology uses 12, but Tayeb wants tighter
- Example: 1km distance requires at least 100m head
- Horizontal distance between dam walls divided by elevation difference

### Reservoir Capacity
- Minimum: 1M cubic meters per dam
- Both dams in a pair must meet this threshold

## Deeper Filters (Tier 2, more expensive to compute)

### Protected Areas
- Exclude pairs where the connection route passes through WDPA protected areas
- Buffer: 1km around protected boundaries

### Reservoir Fill Rate
- Soufiane: exclude dams below 5-10% average fill
- Tayeb: ideally above 40-50% filled
- Morocco has experienced severe drought for 7 years, most dams at 20-30% capacity
- Thresholds are configurable
- Data source: Moroccan government daily capacity website (pending from Soufiane)
- If fill data unavailable, skip this filter and note it

### Grid Proximity
- Distance to nearest high-voltage substation or transmission line
- Important but not a hard cutoff (Soufiane: "ideal scenario factor")
- Used in scoring, not as elimination filter

## PSH Configurations

Three valid configurations for any pair:
1. Two existing dams (primary focus, Package 1)
2. Existing dam as lower reservoir + new dam built upstream (Package 2)
3. Existing dam as upper reservoir + new dam built downstream (less likely, Package 2)

For Package 1, only configuration 1 applies.

## Cost Benchmarks

### Battery Storage
- ~$100,000 per MWh (from Tayeb)

### PSH
- Tayeb has detailed costing from ~10 years ago for full PSH facility
- Numbers to be updated and shared
- Depreciation period: 30 years average
  - Reservoirs: 30-40 years
  - Electromechanical equipment: 20 years

### Dam Age
- Generally not a screening concern (Ben-Louis Dam is 75 years old, performing fine)
- Include as informational output field, not a filter

## Scoring Weights (from technical call)

| Dimension | Default Weight |
|-----------|---------------|
| Cost competitiveness (PSH $/MWh vs battery) | 30% |
| Energy potential | 25% |
| Grid proximity | 20% |
| Reservoir suitability (fill rate, capacity, condition) | 15% |
| Regulatory risk (protected areas, competing water uses) | 10% |

Run with at least 3 weight distributions for sensitivity.
