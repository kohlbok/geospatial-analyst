$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $RepoRoot ".venv"

function Header($msg) { Write-Host "`n==> $msg" -ForegroundColor Blue }
function Success($msg) { Write-Host "  OK: $msg" -ForegroundColor Green }
function Fail($msg) { Write-Error "  FAIL: $msg"; exit 1 }

# ---------- Python ----------
Header "Checking Python"

$Python = $null
foreach ($candidate in @("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python")) {
    try {
        $versionOutput = & $candidate --version 2>&1
        if ($versionOutput -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $Python = (Get-Command $candidate).Source
                break
            }
        }
    } catch {
        continue
    }
}

if (-not $Python) {
    Fail "Python 3.10+ is required. Install from https://www.python.org/downloads/"
}
Success "Found $Python"

# ---------- Virtual environment ----------
Header "Setting up virtual environment"

if (-not (Test-Path $VenvDir)) {
    & $Python -m venv $VenvDir
    Success "Created $VenvDir"
} else {
    Success "$VenvDir already exists"
}

$Pip = Join-Path $VenvDir "Scripts/pip"
$Py = Join-Path $VenvDir "Scripts/python"

# ---------- Upgrade pip ----------
Header "Upgrading pip"
& $Pip install --upgrade pip setuptools wheel -q
Success "pip upgraded"

# ---------- Install Python dependencies ----------
Header "Installing Python dependencies"
& $Pip install -r (Join-Path $RepoRoot "requirements.txt") -q
Success "All packages installed"

# ---------- Verify critical imports ----------
Header "Verifying imports"

& $Py -c @"
import sys
failures = []
packages = [
    ('geopandas', 'geopandas'),
    ('rasterio', 'rasterio'),
    ('shapely', 'shapely'),
    ('pyogrio', 'pyogrio'),
    ('folium', 'folium'),
    ('pandas', 'pandas'),
    ('numpy', 'numpy'),
    ('scipy', 'scipy'),
    ('scikit-image', 'skimage'),
    ('scikit-learn', 'sklearn'),
    ('openpyxl', 'openpyxl'),
    ('simplekml', 'simplekml'),
    ('orjson', 'orjson'),
    ('requests', 'requests'),
    ('matplotlib', 'matplotlib'),
    ('fastmcp', 'fastmcp'),
    ('overpy', 'overpy'),
    ('jinja2', 'jinja2'),
]
optional = [
    ('weasyprint', 'weasyprint'),
]
for name, module in packages:
    try:
        __import__(module)
    except ImportError as e:
        failures.append(f'{name}: {e}')

warnings = []
for name, module in optional:
    try:
        __import__(module)
    except ImportError:
        warnings.append(name)

if failures:
    print('Import failures:')
    for f in failures:
        print(f'  - {f}')
    sys.exit(1)
else:
    print(f'All {len(packages)} packages import successfully')
    if warnings:
        print('Optional (PDF export): ' + ', '.join(warnings) + ' not available')
"@

Success "All imports verified"

# ---------- Create directories ----------
Header "Creating directory structure"

$dirs = @("data\.cache\srtm", "data\.cache\raw", "data\.cache\intermediate", "output")
foreach ($dir in $dirs) {
    $path = Join-Path $RepoRoot $dir
    if (-not (Test-Path $path)) { New-Item -ItemType Directory -Path $path -Force | Out-Null }
}
Success "Directories ready"

# ---------- Generate .mcp.json ----------
Header "Generating .mcp.json"

$Template = Join-Path $RepoRoot ".mcp.json.template"
$McpOutput = Join-Path $RepoRoot ".mcp.json"

if (-not (Test-Path $Template)) {
    Fail ".mcp.json.template not found"
}

$content = Get-Content $Template -Raw
$content = $content -replace '\{\{PYTHON_PATH\}\}', '.venv/Scripts/python'
Set-Content -Path $McpOutput -Value $content -NoNewline
Success ".mcp.json configured"

# ---------- Summary ----------
Header "Setup complete"
Write-Host ""
Write-Host "  Workflow:"
Write-Host "    1. Open Claude Code: claude"
Write-Host "    2. Drop your data files into data/"
Write-Host "    3. /collect-dams [country]   (optional, scrapes global databases)"
Write-Host "    4. /normalize-dams           (standardize columns into the screening schema)"
Write-Host "    5. /screen-dams              (find pairs between existing dams)"
Write-Host "    6. /scan-terrain             (find new reservoir sites for greenfield siting)"
Write-Host ""
