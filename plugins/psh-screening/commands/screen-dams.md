# /screen-dams

Screen all dams for pumped storage hydropower (PSH) potential.

## Skills

Load: methodology, constraints

## Gates

This command has explicit checkpoints where you MUST stop and wait for user confirmation before continuing. Never skip a gate.

## Steps

### Step 0: Clean Slate

Remove previous results for a fresh run:
- Delete everything in `output/` (old results, maps, PDFs)
- Delete `data/.cache/intermediate/` (stale screening intermediates)
- Do NOT delete `data/.cache/srtm/` or `data/.cache/raw/` (expensive downloads, reusable)

### Step 1: Load Data

Call the `load_dam_registry` MCP tool. It returns total dams and field coverage stats.

Present to the user:
```
Input: data/dams.json
Total dams: X
  Coordinates: X/X
  Elevation: X/X
  Height: X/X
  Capacity: X/X
  Grid distance: X/X
```

--- GATE 1 ---
Ask: "This is the input data. Want to use a different file, or continue?"
WAIT for user response. Do NOT proceed until they confirm.

### Step 2: Assumptions

Read `config/parameters.json`. Present ALL parameters in a clear table:
```
Screening Filters:
  Min head: Xm
  Max distance: Xkm
  Min capacity: X MCM
  Max distance/head ratio: X

Scoring Weights:
  Energy potential: X
  Cost advantage: X
  Grid proximity: X
  Reservoir quality: X

Cost Model:
  Penstock: EUR X/km
  Upper reservoir: EUR X/MCM
  Lower reservoir: EUR X/MCM
  Powerhouse: EUR X/MW
  Fixed costs: EUR X
  Grid connection: $X/km
```

--- GATE 2 ---
Ask: "Want to adjust any of these parameters? Or continue with screening?"
WAIT for user response. Do NOT proceed until they confirm.

### Step 3: Generate and Score Pairs

Call the `generate_pairs` MCP tool, then `screen_pairs`. Report: total pairs evaluated, how many passed filters, top 10 with rank, names, head, distance, energy, LCOE, and score.

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

1. For each top pair, write an honest assessment: why it works (head, capacity, distance), concerns (remoteness, small reservoir, competing water uses), grid connection quality. Verdict: "Strong candidate" / "Worth investigating" / "Marginal".

2. Present the review in chat.

3. Call `generate_executive_summary` MCP tool with the review data as JSON.

4. Read the generated PDF and visually check it renders correctly. Regenerate if needed.

5. Tell user where the PDF was saved.
