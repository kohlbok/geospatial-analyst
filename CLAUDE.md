# Geospatial Analyst

## What This Is

AI-powered geospatial screening tool. Evaluates existing dams for pumped storage hydropower (PSH) potential. Finds dam pairs where pumped storage is technically viable and cost-competitive with battery storage. Currently configured for Morocco, extensible to any country.

## Architecture

```
data/
  *.json, *.xlsx, *.csv            Dam registries. Any number of files, user picks which to use.
  .cache/                          Gitignored: SRTM tiles, raw databases, intermediate files

config/
  parameters.json                  Filters, scoring weights, cost benchmarks (~20 lines)

commands/
  setup.md                         Install deps, configure MCP server

plugins/
  psh-screening/
    commands/
      collect-dams.md              Collect dam data for any country from global databases
      normalize-dams.md            Transform any data file into standard format for screening
      screen-dams.md               Screen collected dams for PSH potential
    skills/
      methodology/SKILL.md         Scoring formulas, energy calculations, process overview
      constraints/SKILL.md         Engineering filter thresholds
      data-sources/SKILL.md        Global and country-specific dam databases
      data-collection-workflow/    How to collect and merge dam data for any country
      visual-review/SKILL.md       Decision tree and methodology for satellite visual review

mcp-servers/
  geospatial/
    server.py                      FastMCP server: 16 MCP tools
    config.py                      Paths, config loading
    geo.py                         Haversine distance calculations
    ingestion/                     Data collection and enrichment
      download.py                  Generic file download utilities
      merge.py                     Tiered proximity + surface area deduplication (Union-Find)
      elevate.py                   SRTM 30m elevation enrichment
      osm.py                       OpenStreetMap grid distance and name lookup
      geocode.py                   Multi-strategy geocoder for dams without coordinates
      under_construction.py        WikiData + OSM under-construction dam fetcher
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
      maps.py                      Interactive Folium maps (screening results + overview)
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
| `load_dam_registry` | List files in data/, select and load one as active |
| `generate_pairs` | Brute-force all dam pair combinations |
| `screen_pairs` | Apply filters, calculate energy/cost, score and rank |
| `generate_map` | Interactive HTML map with satellite imagery |
| `generate_overview_map` | Overview map of all dams color-coded by status (for visual review during collection) |
| `generate_results` | Excel, JSON, 3D KML, GeoJSON exports |
| `generate_executive_summary` | PDF report with expert pair assessments |
| `merge_sources` | Merge all staged dam sources by tiered coordinate proximity and surface area matching |
| `enrich_names` | Canonical names from OpenStreetMap water features |
| `enrich_grid_distance` | Look up nearest HV substation per dam (OpenStreetMap) |
| `enrich_elevation` | Add SRTM 30m elevation data |
| `enrich_coordinates` | Geocode dams without coordinates (OSM, Nominatim) |
| `fetch_under_construction` | Fetch under-construction dams from WikiData and OSM |
| `download_file` | Download any URL to cache |
| `inspect_file` | Inspect any tabular file (columns, sample rows) |
| `parse_tabular` | Parse file with agent-provided column mapping |

## How It Works

- **Skills** are domain knowledge the agent loads: methodology, constraints, data sources
- **Commands** are workflows the agent executes: `/collect-dams` gathers data, `/normalize-dams` transforms it, `/screen-dams` screens for PSH potential
- **MCP server** is the typed tool interface: every operation is an MCP tool with explicit arguments and structured output
- **Data** lives in `data/` as JSON, xlsx, or CSV files. The agent lists what's there and asks the user which file to work with.

## Key Rules

1. All configurable parameters live in `config/parameters.json`. Never hardcode thresholds.
2. Dam data lives in `data/`. Never hardcode a specific filename. The agent lists available files and asks the user which one to use.
3. Output goes to `output/`. Keep it minimal: one Excel, one map, one JSON, one KML, one GeoJSON.
4. Cache files (SRTM tiles, raw databases, intermediates) go in `data/.cache/`, never shown to user.
5. `parse_tabular` preserves all columns. Mapped columns get standard names, unmapped columns pass through as-is.

## Adding Commands

1. Write the command file at `plugins/psh-screening/commands/{command-name}.md`. This is the source of truth.
2. Create a symlink so Claude Code can load it as a slash command: `mkdir -p .claude/skills/{command-name} && ln -s ../../../plugins/psh-screening/commands/{command-name}.md .claude/skills/{command-name}/SKILL.md`
3. Update the architecture section above.

## Style

No code comments. Self-explanatory code. No em dashes. Functions should be short and focused.
