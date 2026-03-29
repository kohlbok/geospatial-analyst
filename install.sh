#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_MIN="3.10"
VENV_DIR=".venv"

header() { printf "\n\033[1;34m==> %s\033[0m\n" "$1"; }
success() { printf "\033[1;32m  OK: %s\033[0m\n" "$1"; }
fail() { printf "\033[1;31m  FAIL: %s\033[0m\n" "$1"; exit 1; }

# ---------- Python ----------
header "Checking Python"

PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$("$candidate" -c "import sys; print(sys.version_info.major)")
        minor=$("$candidate" -c "import sys; print(sys.version_info.minor)")
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python >= $PYTHON_MIN is required. Install it with: brew install python@3.12"
fi
success "Found $PYTHON ($version)"

# ---------- Virtual environment ----------
header "Setting up virtual environment"

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON" -m venv "$VENV_DIR"
    success "Created $VENV_DIR"
else
    success "$VENV_DIR already exists"
fi

source "$VENV_DIR/bin/activate"
success "Activated $VENV_DIR ($(python --version))"

# ---------- Upgrade pip ----------
header "Upgrading pip"
pip install --upgrade pip setuptools wheel -q
success "pip $(pip --version | awk '{print $2}')"

# ---------- Install Python dependencies ----------
header "Installing Python dependencies"
pip install -r requirements.txt -q
success "All packages installed"

# ---------- Verify critical imports ----------
header "Verifying imports"

python -c "
import sys
failures = []
packages = [
    ('geopandas', 'geopandas'),
    ('rasterio', 'rasterio'),
    ('shapely', 'shapely'),
    ('fiona', 'fiona'),
    ('folium', 'folium'),
    ('pandas', 'pandas'),
    ('numpy', 'numpy'),
    ('openpyxl', 'openpyxl'),
    ('simplekml', 'simplekml'),
    ('requests', 'requests'),
    ('matplotlib', 'matplotlib'),
    ('fastmcp', 'fastmcp'),
    ('overpy', 'overpy'),
    ('jinja2', 'jinja2'),
    ('weasyprint', 'weasyprint'),
]
for name, module in packages:
    try:
        __import__(module)
    except ImportError as e:
        failures.append(f'{name}: {e}')

if failures:
    print('Import failures:')
    for f in failures:
        print(f'  - {f}')
    sys.exit(1)
else:
    print(f'All {len(packages)} packages import successfully')
"
success "All imports verified"

# ---------- Create directories ----------
header "Creating directory structure"

mkdir -p data/.cache/srtm data/.cache/raw data/.cache/intermediate
mkdir -p output
success "Directories ready"

# ---------- Summary ----------
header "Setup complete"
echo ""
echo "  To activate the environment:"
echo "    source $VENV_DIR/bin/activate"
echo ""
echo "  To screen dams:"
echo "    claude"
echo "    /screen-dams"
echo ""
