# /package

Create a distributable zip of the project, excluding large dependencies and cache data.

## What is included

- `config/` (parameters.json)
- `commands/` (all command files)
- `plugins/` (skills, methodology, commands)
- `templates/` (executive summary HTML)
- `mcp-servers/` (all Python code)
- `scripts/` (render scripts)
- `data/*.json`, `data/*.xlsx` (dam registries only, not cache)
- `data/raw/staging/` (staged source manifests)
- `output/` (if it has results)
- `install.sh`, `install.ps1`
- `CLAUDE.md`, `pyproject.toml`, `requirements.txt` or similar
- `.claude/` config (skills symlinks, settings.local.json)

## What is excluded

- `.venv/`, `node_modules/`
- `data/.cache/` (SRTM tiles, raw databases, intermediates)
- `__pycache__/`, `*.pyc`
- `.git/`
- Any file over 50MB

## Steps

1. Run `git ls-files` to get tracked files, plus any output files the user wants to include.
2. Show the estimated zip size and file count.
3. Ask the user where to save it (default: `../{project-name}-{date}.zip`, next to the project directory).
4. Create the zip.
5. Report the final size and path.
