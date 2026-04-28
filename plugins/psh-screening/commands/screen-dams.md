# /screen-dams

Screen all dams for pumped storage hydropower (PSH) potential.

## Platform

Before doing anything else, run `uname` once to decide which interface to use for the rest of this command:
- Output starts with `Darwin` or `Linux`: use the `mcp__geospatial__*` tools as written below.
- Output contains `MINGW`, `MSYS`, `CYGWIN`, `Windows_NT`, or `uname` is not found: the MCP server is unreliable on Windows. Use the CLI fallback instead. Every MCP tool below has an exact CLI equivalent:

  ```
  .venv/Scripts/python.exe mcp-servers/geospatial/cli.py <tool_name> [--arg value ...]
  ```

  Subcommand names match MCP tool names exactly. Keyword args become `--name value` flags. JSON output is printed to stdout — parse it the same as the MCP response. Examples:
  - `mcp__geospatial__cleanup(targets="screen")` → `... cli.py cleanup --targets screen`
  - `mcp__geospatial__load_dam_registry(file="dams.json")` → `... cli.py load_dam_registry --file dams.json`
  - `mcp__geospatial__generate_pairs()` → `... cli.py generate_pairs`
  - `mcp__geospatial__screen_pairs()` → `... cli.py screen_pairs`
  - `mcp__geospatial__generate_executive_summary(expert_review='[{...}]')` → `... cli.py generate_executive_summary --expert_review '[{...}]'`

  For each step below, translate every `mcp__geospatial__<tool>(args...)` call into the equivalent CLI invocation.

## Skills

Load: methodology, constraints

## Gates

This command has explicit checkpoints where you MUST stop and wait for user confirmation before continuing. Never skip a gate.

## Steps

### Step 0: Clean Slate

Call the `cleanup` MCP tool with `targets="screen"`. This removes everything in `output/` and `data/.cache/intermediate/` while preserving `data/.cache/srtm/` and `data/.cache/raw/` (expensive downloads, reusable).

### Step 1: Load Data

Call `load_dam_registry` with no arguments to list available files in `data/`. Ask the user which file to screen.

Once they pick a file, call `load_dam_registry` with that filename.

If it returns `needs_parsing`, the file hasn't been normalized yet. Tell the user:
"This file needs to be normalized first. Run /normalize-dams to convert it to the standard format."
STOP here.

Otherwise, present the coverage stats:
```
Input: [filename]
Total dams: X
  Coordinates: X/X
  Elevation: X/X
  Height: X/X
  Capacity: X/X
  Grid distance: X/X
```

If elevation or grid distance coverage is low, suggest running enrichment before screening.

--- GATE 1 ---
Ask: "This is the input data. Want to use a different file, or continue?"
WAIT for user response. Do NOT proceed until they confirm.

### Step 2: Assumptions

Read `config/parameters.json`. The file uses `{"value": X, "description": "..."}` format. Present parameters grouped by what the user can tune, with descriptions so they understand what each one does.

Use this format -- show the description for every parameter:

```
SCREENING FILTERS (pairs that fail any of these are excluded)
  Min head:                100m     -- Minimum elevation difference. Below this, energy output is too low.
  Max distance:            40km     -- Maximum distance between dams. Beyond this, penstock costs dominate.
  Min capacity:            1.5 MCM  -- Both reservoirs must hold at least this much water.
  Max distance/head ratio: 50       -- Long tunnels for little elevation gain are uneconomic.

SCORING WEIGHTS (how the composite score is calculated, must sum to 1.0)
  Energy potential:   0.40  -- Favors pairs with large head and reservoir volume (the core physics).
  Cost advantage:     0.35  -- Favors pairs where PSH CAPEX/MWh beats the battery benchmark.
  Grid proximity:     0.25  -- Favors pairs close to existing HV substations (only size-independent metric).

COST MODEL (component costs that build up total project CAPEX)
  Penstock:           EUR 43M/km    -- Pressure pipe between dams. Major cost driver for distant pairs.
  Upper reservoir:    EUR 14M/MCM   -- Upper dam preparation costs.
  Lower reservoir:    EUR 36M/MCM   -- Lower dam preparation costs (higher civil works).
  Powerhouse:         EUR 490K/MW   -- Turbine and generator facility.
  Tunneling:          EUR 6.5M/km   -- Tunnel boring where terrain requires it.
  Fixed costs:        EUR 42M       -- Engineering, permitting, access roads.
  Grid connection:    $1M/km        -- HV line to nearest substation.

  -> Total CAPEX is calculated per pair from these components.
  -> CAPEX per MWh = Total CAPEX / energy storage capacity (the primary cost metric).
  -> LCOE = Total CAPEX / (energy x 300 cycles/year x 40 years).

BATTERY BENCHMARK (what PSH is compared against)
  Battery CAPEX:      $100,000/MWh  -- If a pair's CAPEX/MWh is lower, PSH wins.

ENERGY PHYSICS
  Round-trip efficiency: 78%        -- 22% energy loss per pump/generate cycle.
  Usable reservoir:      60%        -- Fraction of reservoir volume available for PSH.
  Power duration:        8 hours    -- Hours of continuous output at rated capacity.
```

--- GATE 2 ---
Ask: "Want to adjust any of these parameters? Or continue with screening?"
WAIT for user response. Do NOT proceed until they confirm.

### Step 3: Generate and Score Pairs

Call the `generate_pairs` MCP tool, then `screen_pairs`. Report: total pairs evaluated, how many passed filters, top 10 with rank, names, head, distance, energy, CAPEX/MWh, CAPEX advantage vs battery, LCOE, and composite score.

### Step 4: Outputs

Call `generate_map` and `generate_results` MCP tools.

--- GATE 3 ---
Ask: "Where should I put the output? Default is `output/` in this repo."
WAIT for user response. If they give a custom path, copy all files there.

Tell the user where the files are:
- `results.xlsx` -- formatted workbook (Dam Registry + Pairs Ranked + Assumptions)
- `results.json` -- machine-readable results
- `map.html` -- interactive map with satellite imagery
- `top_pairs_3d.kml` -- 3D terrain view for Google Earth
- `pairs.geojson` -- for GIS tools

### Step 5: Expert Review + Executive Summary (optional)

--- GATE 4 ---
Ask: "Want me to review the top pairs and generate an executive summary PDF?"
WAIT for user response.

If yes:

1. For each top pair, write an honest assessment: why it works (head, capacity, distance), CAPEX/MWh vs the battery benchmark, concerns (remoteness, small reservoir, competing water uses), grid connection quality. Verdict: "Strong candidate" / "Worth investigating" / "Marginal".

2. Present the review in chat.

3. Call `generate_executive_summary` MCP tool with the review data as JSON. Each pair must include: rank, upper_dam, lower_dam, head_m, distance_km, energy_mwh, capex_per_mwh_usd, capex_advantage_pct, score, grid_distance_km, verdict, assessment.

4. If PDF generation succeeds, read the generated PDF and visually check it renders correctly. Regenerate if needed. Tell user where the PDF was saved.

5. If PDF generation fails (e.g. weasyprint not available on Windows), tell the user the HTML version was saved instead at `output/executive-summary.html` and can be opened in any browser or printed to PDF from there.
