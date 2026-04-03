# /cleanup

Remove generated outputs and temporary files for a fresh start.

## What gets deleted

- `output/*` (results, maps, PDFs, KML, GeoJSON)
- `data/.cache/intermediate/` (screening intermediates)

## What is kept

- `data/.cache/srtm/` (SRTM elevation tiles, expensive to re-download)
- `data/.cache/raw/` (downloaded source databases)
- `data/*.json`, `data/*.xlsx` (dam registries)
- `data/raw/staging/` (staged source files)
- Everything in `config/`, `mcp-servers/`, `plugins/`, `templates/`

## Steps

1. Show what will be deleted with file counts and sizes.
2. Ask the user to confirm before deleting.
3. Delete the files.
4. Report what was removed.
