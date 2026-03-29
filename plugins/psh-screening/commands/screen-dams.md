# /screen-dams

Screen all dams for pumped storage hydropower (PSH) potential.

## Skills

Load: methodology, constraints

## Steps

### Step 1: Load Data

Read `data/dams.json`. Report: total dams, field coverage (elevation, capacity, grid distance), any data quality issues (missing fields, duplicates within 1km, coordinates outside bbox). Keep it brief.

### Step 2: Assumptions

Read `config/parameters.json`. Present the filters, scoring weights, and cost benchmarks. Ask if user wants to adjust anything.

### Step 3: Generate and Score Pairs

Call `generate_pairs` then `screen_pairs`. Report: total pairs evaluated, how many passed filters, top 10 with rank, names, head, distance, energy, and score.

### Step 4: Outputs

Call `generate_map` and `generate_results`. Tell user where files are:
- `output/results.xlsx` -- formatted workbook (Dam Registry + Pairs Ranked + Assumptions)
- `output/results.json` -- machine-readable results
- `output/map.html` -- interactive map with satellite imagery (open in browser)
- `output/top_pairs_3d.kml` -- 3D terrain view of top pairs (open in Google Earth)
- `output/pairs.geojson` -- for GIS tools

### Step 5: Expert Review + Executive Summary (optional)

Ask: "Want me to review the top 10 pairs and generate an executive summary PDF?"

If yes:

1. For each of the top 10 pairs, write a brief honest assessment covering:
   - Why it works (head, capacity, distance)
   - Concerns (remoteness, small reservoir, competing water uses based on purpose field)
   - Grid connection quality (distance, voltage)
   - Verdict: one of "Strong candidate" / "Worth investigating" / "Marginal"

2. Present the review to the user in chat.

3. Call `generate_executive_summary` with the expert review data as a JSON list. Each entry needs: rank, upper_dam, lower_dam, head_m, distance_km, energy_mwh, score, grid_distance_km, verdict (one of "Strong candidate" / "Worth investigating" / "Marginal"), assessment (HTML string with `<p><strong>Why it works:</strong>...`, `<strong>Concerns:</strong>...`, `<strong>Grid connection:</strong>...`).

4. Read the generated PDF (`output/executive-summary.pdf`) and visually review it. Check that:
   - Cover page looks clean with no overflow
   - Stats, table, and pair cards render properly
   - No floating point numbers (use rounded values)
   - Page breaks fall in sensible places (not mid-card)
   - All 10 pair assessments have substantive analysis (not generic filler)
   If anything looks off, adjust the report data and regenerate.

5. Tell user: "Executive summary saved to `output/executive-summary.pdf`"
