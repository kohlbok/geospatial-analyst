# /normalize-dams

Transform any data file in `data/` into the standard format for screening.

## Platform

Before doing anything else, run `uname` once to decide which interface to use for the rest of this command:
- Output starts with `Darwin` or `Linux`: use the `mcp__geospatial__*` tools as written below.
- Output contains `MINGW`, `MSYS`, `CYGWIN`, `Windows_NT`, or `uname` is not found: the MCP server is unreliable on Windows. Use the CLI fallback instead. Every MCP tool below has an exact CLI equivalent:

  ```
  .venv/Scripts/python.exe mcp-servers/geospatial/cli.py <tool_name> [--arg value ...]
  ```

  Subcommand names match MCP tool names exactly. Keyword args become `--name value` flags. JSON output is printed to stdout — parse it the same as the MCP response. Examples:
  - `mcp__geospatial__load_dam_registry(file="dams.xlsx")` → `... cli.py load_dam_registry --file dams.xlsx`
  - `mcp__geospatial__inspect_file(path="data/dams.xlsx")` → `... cli.py inspect_file --path data/dams.xlsx`
  - `mcp__geospatial__parse_tabular(path=..., column_mapping='{"name":"Dam"}', output_name="dams")` → `... cli.py parse_tabular --path ... --column_mapping '{"name":"Dam"}' --output_name dams`

  For each step below, translate every `mcp__geospatial__<tool>(args...)` call into the equivalent CLI invocation.

## Skills

Load: data-collection-workflow

## Steps

### Step 1: Pick File

Call `load_dam_registry` with no arguments to list all files in `data/`. Ask the user which file to normalize.

Once they pick a file, call `inspect_file` on it to see columns, types, and sample rows.

### Step 2: Map Columns

Look at the columns and figure out which ones map to the required fields:

**Required:** `name`, `lat`, `lon`

**Standard optional:** `elevation_m`, `capacity_mcm`, `height_m`, `grid_distance_km`, `year_built`, `purpose`, `status`, `region`

Use the column mapping cheat sheet from data-collection-workflow for common names. Present the mapping to the user:

```
Column mapping:
  "Dam Name" -> name
  "Latitude" -> lat
  "Longitude" -> lon
  "Capacity (M m3)" -> capacity_mcm
  "Dam Height (m)" -> height_m
  ...

Columns kept as-is (passthrough):
  "Fill Rate (%)" -> fill_rate_pct
  "HV Line (km)" -> hv_line_km
  "Visual Notes" -> visual_notes
  ...
```

All columns not mapped to a standard field get passed through with a cleaned-up key name (lowercase, underscores, no special characters). Nothing gets dropped.

Ask: "Does this mapping look right? Any columns I should rename or skip?"

WAIT for confirmation.

### Step 3: Parse

Call `parse_tabular` with the confirmed column mapping. Use the source filename (without extension) as the output_name.

Report: "Parsed X records (Y with coordinates, Z with names)"

### Step 4: Save

The parsed JSON is now in staging. Call `merge_sources` to produce the final file. This writes to `data/` as a JSON file.

If this is a single-file normalize (not a multi-source collect), tell the user the output path and ask if they want to set it as the active file for screening.

### Step 5: Enrich (if needed)

Check what the data is missing:
- If no `elevation_m`: call `enrich_elevation`
- If no `grid_distance_km`: call `enrich_grid_distance`

Only enrich fields that are actually missing. Report what was added.

### Step 6: Done

```
Normalized [filename] -> [output_path]
  Total records: X
  With coordinates: Y
  With elevation: Z
  With capacity: W

Ready for /screen-dams.
```
