# Geospatial Analyst

## What This Is

AI employee for Clean Energy Bridge. First job: screen Morocco's ~285 existing dams for pumped storage hydropower (PSH) potential. Finds dam pairs where pumped storage is technically viable and cost-competitive with battery storage.

## Architecture

```
plugins/
└── psh-screening/             Morocco PSH screening workflow
    ├── commands/              Runnable workflows
    │   └── screen-dams.md     Main command: end-to-end PSH screening
    └── skills/                Domain knowledge loaded by commands
        ├── methodology/       NREL PSH screening methodology, scoring approach
        ├── data-sources/      What databases exist, how to get them, how to parse them
        └── constraints/       Engineering constraints from Tayeb/Soufiane

mcp-servers/
└── geospatial/                Typed tool interface for all geospatial operations
    └── server.py              FastMCP server: download, merge, elevate, screen, score, visualize

scripts/
└── (standalone utilities if needed)

config/
└── parameters.json            All configurable constraints, weights, thresholds

data/
├── raw/                       Downloaded source databases (gitignored)
└── processed/                 Cleaned, merged, enriched data (JSON)

output/                        Generated results (gitignored)
├── maps/                      Interactive HTML maps, KML, GeoJSON
├── reports/                   Terrain profiles, pair analysis
└── exports/                   Excel workbooks, JSON ranked lists
```

## How It Works

- **Skills** are domain knowledge the agent loads: methodology, data source docs, engineering constraints from CEB's team
- **Commands** are workflows the agent executes: they orchestrate MCP tools in sequence
- **MCP server** is the typed tool interface: every geospatial operation (download, merge, filter, score, visualize) is an MCP tool with explicit arguments and structured output

## Key Rules

1. All configurable parameters live in `config/parameters.json`. Never hardcode thresholds.
2. Every filter decision must be logged with a rationale. No silent eliminations.
3. Use coordinate proximity (500m) as the primary merge key across databases, not dam names.
4. Run energy calculations at three fill levels (conservative, standard, optimistic).
5. Generate outputs in all formats: Excel workbook, interactive HTML maps, JSON, KML/GeoJSON.

## Style

No code comments. Self-explanatory code. No em dashes. Functions should be short and focused.
