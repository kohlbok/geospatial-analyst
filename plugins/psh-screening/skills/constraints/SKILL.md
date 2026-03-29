# Engineering Constraints

## Screening Filters

Applied to all dam pairs. Values configured in `config/parameters.json`.

| Filter | Default | Purpose |
|--------|---------|---------|
| Minimum head | 100m | Below this, energy output is too low to justify infrastructure |
| Maximum distance | 30km | Beyond this, penstock/tunnel costs dominate |
| Minimum capacity | 1 MCM | Both reservoirs must hold enough water for meaningful storage |

## Grid Proximity

Distance to nearest high-voltage substation (>=60kV). Not a hard cutoff but used in scoring. Closer to grid = lower interconnection cost = higher score.

## Factors NOT Used as Filters (informational only)

- **Dam age**: Old dams can be fine. Include in output but don't filter on it.
- **Protected areas**: Flag if nearby, factor into scoring, but don't auto-eliminate.
- **Fill rate**: Important but requires country-specific operational data that may not be available. Skip if no data.
