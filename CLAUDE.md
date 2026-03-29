# Geospatial Analyst

## What This Is

AI-powered geospatial screening tool. Evaluates existing dams for pumped storage hydropower (PSH) potential. Finds dam pairs where pumped storage is technically viable and cost-competitive with battery storage. Currently configured for Morocco, extensible to any country.

## Architecture

```
data/
  dams.json                        THE input: clean dam registry with coords, elevation, capacity, grid distance
  dams.xlsx                        Same as Excel for non-technical users
  .cache/                          Gitignored: SRTM tiles, raw databases, intermediate files

config/
  parameters.json                  Filters, scoring weights, cost benchmarks (~20 lines)

plugins/
  psh-screening/
    commands/
      screen-dams.md               Main command: end-to-end PSH screening workflow
    skills/
      methodology/SKILL.md         Scoring formulas, energy calculations, process overview
      constraints/SKILL.md         Engineering filter thresholds
      data-sources/SKILL.md        Global and country-specific dam databases
      data-collection-workflow/    How to collect and merge dam data for any country

mcp-servers/
  geospatial/
    server.py                      FastMCP server: 11 MCP tools
    config.py                      Paths, config loading
    geo.py                         Haversine distance calculations
    ingestion/                     Data collection and enrichment
      download.py                  Database downloaders (FAO, GeoDAR, HydroLAKES)
      merge.py                     Dam registry deduplication and merging
      elevate.py                   SRTM 30m elevation enrichment
      osm.py                       OpenStreetMap grid distance lookup
      inspect.py                   Generic file inspection (CSV, Excel, Shapefile)
      parse.py                     Generic tabular parsing with column mapping
      staging.py                   Staging area for agent-driven data collection
    screening/
      pairs.py                     Brute-force pair generation with head/distance calc
      filters.py                   Engineering constraint filters
    scoring/
      energy.py                    Energy potential: head x volume x efficiency
      cost.py                      PSH vs battery cost comparison
      composite.py                 Weighted composite scoring
    terrain/
      profiles.py                  SRTM elevation profiles between dam pairs
    visualization/
      maps.py                      Interactive Folium map with satellite imagery
      export.py                    Excel (styled), JSON, 3D KML, GeoJSON output
      terrain_viz.py               Terrain profile charts

scripts/
  render_report.py                 Jinja2 + WeasyPrint: renders executive summary HTML to PDF

templates/
  executive-summary.html           A4 PDF template matching Varia design system

output/                            Generated results (gitignored)
  results.xlsx                     Formatted workbook (Dam Registry, Pairs Ranked, Assumptions)
  results.json                     Machine-readable results
  map.html                         Interactive map with satellite imagery
  top_pairs_3d.kml                 3D terrain view for Google Earth
  pairs.geojson                    For GIS tools
  executive-summary.pdf            Expert review report (generated on demand)
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `load_dam_registry` | Load dams from data/dams.json |
| `generate_pairs` | Brute-force all dam pair combinations |
| `screen_pairs` | Apply filters, calculate energy/cost, score and rank |
| `generate_map` | Interactive HTML map with satellite imagery |
| `generate_results` | Excel, JSON, 3D KML, GeoJSON exports |
| `generate_executive_summary` | PDF report with expert pair assessments |
| `enrich_grid_distance` | Look up nearest HV substation per dam (OpenStreetMap) |
| `enrich_elevation` | Add SRTM 30m elevation data |
| `download_file` | Download any URL to cache |
| `inspect_file` | Inspect any tabular file (columns, sample rows) |
| `parse_tabular` | Parse file with agent-provided column mapping |

## How It Works

- **Skills** are domain knowledge the agent loads: methodology, constraints, data sources
- **Commands** are workflows the agent executes: `/screen-dams` orchestrates load, validate, score, output
- **MCP server** is the typed tool interface: every operation is an MCP tool with explicit arguments and structured output
- **Data** lives in `data/dams.json`, a single clean file the agent reads and the user can edit

## Key Rules

1. All configurable parameters live in `config/parameters.json`. Never hardcode thresholds.
2. Dam data input is `data/dams.json`. All enrichment (elevation, grid distance) gets cached back into this file.
3. Output goes to `output/`. Keep it minimal: one Excel, one map, one JSON, one KML, one GeoJSON.
4. Cache files (SRTM tiles, raw databases, intermediates) go in `data/.cache/`, never shown to user.

## Style

No code comments. Self-explanatory code. No em dashes. Functions should be short and focused.
