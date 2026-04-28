# Geospatial Analyst

AI-powered geospatial screening tool for pumped storage hydropower (PSH). Evaluates existing dams to identify pairs where pumped storage is technically viable and economically competitive with battery storage, and scans surrounding terrain for greenfield reservoir sites. Currently configured for Morocco and extensible to any country by editing a single configuration file.

## Overview

The tool combines a deterministic geospatial backend (Python, SRTM elevation data, OpenStreetMap, watershed analysis) with an AI agent layer (Claude Code) that orchestrates data collection, normalization, screening, and reporting through typed MCP tools. All scoring formulas, engineering constraints, and cost benchmarks live in `config/parameters.json`. Nothing is hardcoded.

Two workflows are supported:

1. **Existing-pair screening.** Pair every dam with every other dam, apply engineering filters (head, distance, capacity, distance-to-head ratio, installed power, energy per cycle), compute energy potential and project CapEx, and rank pairs by a weighted composite score (energy potential, cost advantage versus battery, proximity to grid).
2. **Greenfield siting.** For each existing dam, scan the surrounding terrain at SRTM 30m resolution, detect candidate basins via watershed delineation and saddle search, run a per-candidate two-dimensional optimization over fill depth and penstock diameter, and rank surviving candidates by a CapEx-per-MWh composite score.

Both workflows produce a styled Excel workbook, an interactive Folium map with satellite imagery, a 3D KML for Google Earth, a GeoJSON for GIS tools, and an expert-review PDF.

## Repository Layout

```
config/parameters.json     All filters, scoring weights, cost benchmarks, physics constants
data/                      Dam registries (JSON, xlsx, CSV). Drop new files here.
data/.cache/               SRTM tiles, raw downloads, intermediate artifacts (gitignored)
output/                    Generated results (gitignored)

plugins/psh-screening/
  commands/                Slash-command workflows the agent executes
  skills/                  Domain knowledge the agent loads on demand

mcp-servers/geospatial/    FastMCP server exposing every operation as a typed tool
  ingestion/               Download, merge, geocode, elevate, OSM enrichment
  screening/               Pair generation and engineering filters
  scoring/                 Energy, cost, composite scoring
  terrain/                 SRTM elevation profiles and DEM utilities
  siting/                  Watershed basin detection and CapEx optimization
  visualization/           Maps, Excel, KML, GeoJSON, terrain profile PDFs

scripts/render_report.py   Jinja2 plus WeasyPrint PDF rendering
templates/                 HTML templates for the executive summary PDF
```

A more detailed map of every module lives in `CLAUDE.md`.

## Installation

Requirements: Python 3.10 or newer, git, and Claude Code.

Open the repository in Claude Code and run:

```
/setup
```

That handles everything: it detects the platform, creates a virtual environment in `.venv/`, installs `requirements.txt`, generates `.mcp.json` from the template with the correct Python path, and verifies the MCP server starts. Start a new Claude Code session afterward so the MCP server is connected.

If you prefer to run the installer manually, invoke it directly:

- macOS or Linux: `bash install.sh`
- Windows: `powershell -ExecutionPolicy Bypass -File install.ps1`

### Platform Note

On macOS and Linux, the agent calls `mcp__geospatial__*` tools directly. On Windows the MCP server is unreliable, so every command falls back to an equivalent CLI invocation: `.venv/Scripts/python.exe mcp-servers/geospatial/cli.py <tool_name> [--arg value ...]`. Subcommand names match the MCP tool names exactly. Each command file documents the fallback explicitly.

## Usage

The agent drives every workflow through slash commands. Drop a dam registry into `data/` (or run `/collect-dams` to gather one), then invoke one of:

| Command | Purpose |
|---------|---------|
| `/setup` | Install dependencies and configure the MCP server for the current platform |
| `/collect-dams [country]` | Pull dam data from global databases (GRanD, GOODD, WikiData, OSM) and stage it for merging |
| `/normalize-dams` | Inspect any file in `data/` and transform it into the standard screening schema |
| `/screen-dams` | Pair-screening workflow: filters, energy, cost, composite ranking, full output bundle |
| `/scan-terrain` | Greenfield siting: watershed scan, per-candidate optimization, ranked candidates |
| `/package` | Bundle all generated artifacts for hand-off |
| `/cleanup` | Remove cached intermediates and generated outputs |

Each command file under `plugins/psh-screening/commands/` is the source of truth. The agent loads relevant skills (methodology, constraints, data sources, visual review) before executing.

## Configuration

Every tunable parameter lives in `config/parameters.json`. Each entry uses a `{value, description}` block so the file doubles as inline documentation. Key groups:

- `country`, `country_code`, `bbox`: target country and bounding box
- `filters`: hard cutoffs applied to every pair before scoring (head, distance, capacity, ratio, power, energy)
- `scoring_weights`: composite-score weights for existing-pair screening (must sum to 1.0)
- `cost_benchmarks`, `cost_model`: battery reference cost and component CapEx for the PSH cost model
- `physics`: round-trip efficiency, usable volume fraction, power-duration hours
- `siting`: greenfield siting parameters including basin caps, fill depth, penstock diameter range, friction model, and CapEx limits
- `siting_scoring_weights`: composite-score weights for siting candidates

To screen a different country, change `country`, `country_code`, and `bbox`, adjust grid-tag names under `grid.osm_name_tags` if needed, and rerun `/collect-dams`.

## Outputs

Generated files land in `output/`:

- `results.xlsx` styled workbook with Dam Registry, Pairs Ranked, Assumptions, and a Dam Funnel sheet showing per-dam kill reasons with the closest attempt detail
- `results.json` machine-readable results
- `map.html` interactive map with satellite basemap, pair lines, dam markers, and per-dam popups
- `top_pairs_3d.kml` 3D terrain view for Google Earth
- `pairs.geojson` for downstream GIS tooling
- `executive-summary.pdf` expert-review report
- `siting_results.xlsx`, `siting_map.html`, `siting_profiles.pdf` for the greenfield siting workflow
- `siting_tier1.xlsx`, `siting_tier1_map.html` for the Tier 1 elevation-only viability pass

## Methodology Summary

Energy per cycle uses the standard hydropower formula: `E (MWh) = head * usable_volume * density * gravity * round_trip_efficiency / 3.6e9`. Installed power is derived by dividing energy by a fixed power-duration assumption (default three hours). The cost model is component-based, inflation-adjusted to 2025 dollars, and phase-aware: Phase 1 includes penstock and powerhouse only; Phase 2 adds reservoirs, substation, roads, and other balance-of-plant costs.

For greenfield siting, candidate basins are extracted from SRTM 30m DEMs by detecting topographic sinks, growing watersheds, and locating the saddle that defines the natural reservoir boundary. A constructed wall of bounded height extends each basin. A per-candidate two-dimensional optimization over fill depth and penstock diameter finds the CapEx-per-MWh minimum subject to friction-loss and footprint constraints. Surviving candidates are deduplicated across dams using a BallTree spatial join and ranked by a weighted composite of CapEx per MWh, distance-to-head ratio, and grid distance.

Full methodology, including the derivation of each filter threshold and the Abdelmoumen calibration of penstock unit cost, is documented in `plugins/psh-screening/skills/methodology/SKILL.md`.

## Data Sources

- **GRanD v1.3** global reservoir and dam database (McGill University)
- **GOODD** global georeferenced database of dams
- **WikiData** SPARQL queries for under-construction dams
- **OpenStreetMap** Overpass API for water features, substations, and named infrastructure
- **SRTM 1-arc-second (30m)** and **3-arc-second (90m)** elevation tiles via NASA Earthdata
- **Natural Earth** country boundary polygons
- **Nominatim** and OSM for geocoding dams without coordinates

All raw downloads are cached under `data/.cache/` and re-used across runs.

## License and Attribution

Proprietary. Built for Clean Energy Bridge. SRTM data courtesy of NASA. OpenStreetMap data is licensed under the Open Database License.
