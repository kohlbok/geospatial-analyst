# /scan-terrain

Scan terrain around existing dams to find new reservoir sites for pumped storage hydropower (greenfield siting).

## Skills

Load: methodology, constraints

## Gates

This command has explicit checkpoints where you MUST stop and wait for user confirmation before continuing. Never skip a gate.

## Steps

### Step 0: Clean Slate

Remove previous siting results for a fresh run:
- Delete `output/siting_map.html`, `output/siting_results.xlsx`, `output/siting_profiles.pdf`, `output/siting_tier1.xlsx` if they exist
- Delete `data/.cache/intermediate/siting_tier1.json`, `siting_candidates.json`, `siting_candidates_partial.json`, `siting_scan.log`, `siting_scan.pid` if they exist
- Do NOT delete `data/.cache/srtm/` (expensive SRTM downloads, reusable across runs)
- Do NOT delete `data/.cache/intermediate/scored_pairs.json` (needed to identify dams already paired in the existing-pair screen)

### Step 1: Load Data

Call `load_dam_registry` with no arguments to list available files in `data/`. Ask the user which file to use.

Once they pick a file, call `load_dam_registry` with that filename.

If it returns `needs_parsing`, tell the user to run `/normalize-dams` first. STOP here.

Present coverage stats:
```
Input: [filename]
Total dams: X
  Coordinates: X/X
  Elevation: X/X
  Capacity: X/X
```

Check if `data/.cache/intermediate/scored_pairs.json` exists. If yes, report how many dams were paired in Phase 1 — these still get scanned for greenfield alternatives (a greenfield basin may beat the existing-pair option), but they'll be colored differently on the final map. If no, note that no Phase 1 overlay will appear.

--- GATE 1 ---
Ask: "This is the input data. Want to use a different file, or continue to siting scan?"
WAIT for user response. Do NOT proceed until they confirm.

### Step 2: Parameters

Read `config/parameters.json`, specifically the `siting` section. Present ALL tuneable parameters with descriptions so the user understands what each one does.

Use this format:

```
SEARCH
  Search radius:           20km    -- DEM patch size around each dam.
  Min head:                100m    -- Minimum elevation difference to be viable.
  Max D/H ratio:           15.0    -- Screening buffer. Abdelmoumen reference is 4.0; higher ratios get penalized in scoring.
  Abdelmoumen flag at:     4.0     -- Candidates above this ratio are flagged (not killed).

BASIN DETECTION
  Screening DEM:           90m     -- Resolution for fast elevation-only viability check.
  Basin DEM:               30m     -- Resolution for watershed basin detection.
  Max saddle width:        500m    -- Widest dam wall acceptable at saddle.
  Max wall height:         30m     -- Fill allowed above natural saddle (constructed wall).
  Max fill depth:          30m     -- Tayeb: constructed upper reservoirs are 25-30m embankments above ground.
  Max footprint area:      280,000m² -- ~600m diameter cap. Tayeb: typical 200-500m, max 400-600m.
  Fill depth samples:      20      -- Points on the area-vs-fill curve per basin.
  Max basins per dam:      10      -- Top basins by volume carried to cost optimization.
  Max candidates per dam:  3       -- Top optimized sites kept per dam per direction.

ECONOMICS
  Target power:            330 MW  -- Morocco coal-unit replacement target.
  Min energy:              800 MWh -- Minimum storage. 330 MW x 2.4hr discharge floor. Smaller projects excluded.
  Max total CapEx:         $120M   -- Hard cap. $100k/MWh x 1,200 MWh.
  Battery benchmark:       $100k/MWh -- PSH must beat this to be cost-competitive.
  Marginal threshold:      1.5x    -- Flag candidates within 1.5x battery cost as marginal.

SCORING (composite score, all weights lower-is-better, Tayeb Apr 2026)
  CapEx/MWh:               0.40   -- Primary economic metric.
  Distance/head ratio:     0.40   -- Tayeb: 40%. Abdelmoumen reference is 4.0.
  Grid distance:           0.20   -- Tayeb: 20%. Interconnection cost proxy.

PENSTOCK OPTIMIZATION
  Max friction fraction:   10%     -- Upper bound on head loss (Darcy-Weisbach constraint).
  Darcy friction factor:   0.012   -- Pipe roughness for smooth steel penstock.
  Penstock base rate:      $9.63M/km/m-dia -- Calibrated from Abdelmoumen reference project.
  Diameter range:          1.0-10.0m -- Search range for per-candidate optimization.
  Diameter samples:        20      -- Number of diameter values swept per candidate.

DEDUP
  Merge distance:          500m    -- Candidates within this distance are clustered cross-dam.
```

--- GATE 2 ---
Ask: "Want to adjust any of these parameters? Or continue with Tier 1 viability check?"
WAIT for user response. Do NOT proceed until they confirm.

### Step 3: Tier 1 — Elevation Viability

Call the `tier1_elevation_screen` MCP tool.

Report the funnel results:
```
TIER 1 RESULTS
  Total dams in registry:    X
  Existing PSH excluded:     X   (already-built pumped storage)
  Screened:                  X
  Tier 1 survivors:          X   (have viable head within ratio limit in at least one direction)
  Killed: flat terrain:      X   (no 100m+ elevation change within 20km)
  Killed: ratio too high:    X   (elevation change only at uneconomic distance)
  Killed: other:             X   (missing data)
```

Explain: only existing PSH dams are excluded — Phase 1 paired dams still get scanned (a greenfield partner may beat the existing-pair option). Dams with flat surroundings or where elevation change is only available far away have been eliminated cheaply. The survivors have at least one direction (up or down) where the basic physics work.

Call `generate_tier1_results` to produce intermediate outputs (Excel + map).

Report the output files:
```
TIER 1 OUTPUTS
  siting_tier1.xlsx   -- Funnel summary + all dams with head/distance in each direction
  siting_map.html     -- Dams colored by Tier 1 status
```

--- GATE 3 ---
Ask: "Tier 1 complete. X dams survive. Review the outputs above, then start the background siting scan (basin detection + optimization)?"
WAIT for user response.

### Step 4: Siting Scan — Watershed Basin Detection + Optimization

Call the `siting_scan` MCP tool. This starts a background process that runs watershed basin detection on each surviving dam at 30m resolution, then per-candidate optimization over (fill_depth, penstock_diameter) to minimize CapEx/MWh. Finally, cross-dam deduplication via BallTree merges candidates within 500m.

The scan may take 10 to 30 minutes depending on how many Tier 1 survivors there are. Progress is written to `data/.cache/intermediate/siting_candidates_partial.json` so the scan resumes from interruption.

Set a Monitor tool on `data/.cache/intermediate/siting_scan.log` that tails for four patterns:
1. `\[\d*0/\d+\]` — per-10-dam progress heartbeat (matches `[10/140]`, `[20/140]`, etc.). Relay as a brief status line.
2. `-> \d+ candidates` — a dam produced candidates. Relay as a brief ping.
3. `DONE:` — scan complete. On this, stop the monitor, call `siting_scan_status` once for the full summary, and proceed to Gate 4.
4. `ERROR|Traceback` — failure. Surface immediately.

Do NOT busy-poll `siting_scan_status`. The monitor is event-driven. Only fall back to polling if the monitor goes silent for >10 minutes (means the scan stalled).

Report final results:
```
SITING SCAN RESULTS
  Viable candidates:         X
  Beats battery ($100k/MWh): X
  Marginal (within 1.5x):    X
```

--- GATE 4 ---
Ask: "Scan complete. X viable candidates found. Generate outputs (Excel, map, terrain profiles)?"
WAIT for user response.

### Step 5: Outputs

Call `generate_siting_results` MCP tool.

Report all output files:
```
OUTPUT FILES
  siting_results.xlsx     -- Funnel summary + full candidate table sorted by composite score
  siting_map.html         -- Interactive map: dam status colors + candidate pins with basin footprints
  siting_profiles.pdf     -- Terrain profiles for top 15 candidates
```

Summarize key findings:
- How many candidates beat the $100k/MWh battery benchmark
- The top 3 candidates with their economics (dam name, head, CapEx/MWh, optimal penstock diameter, max discharge)
- Any geographic patterns (e.g., specific mountain ranges or river basins)
- Any Abdelmoumen flags to watch (high D/H ratio candidates that may have penstock friction risk)

Remind the user that this is screening-grade (physics and economics only). The surviving candidates should next go through real-world feasibility checks: land access, protected areas, geology, seismic risk, competing water uses.
