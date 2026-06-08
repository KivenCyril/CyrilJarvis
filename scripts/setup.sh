#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# JARVIS - First-Time Setup Script
# =============================================================================

echo ""
echo "  JARVIS Setup"
echo "  ============"
echo ""

# --- Check Python version ---
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is required but not found."
    echo "Install Python 3.11+ from https://www.python.org/downloads/"
    exit 1
fi

python_version=$(python3 --version 2>&1 | awk '{print $2}')
python_major=$(echo "$python_version" | cut -d. -f1)
python_minor=$(echo "$python_version" | cut -d. -f2)

echo "Python:  $python_version"

if [ "$python_major" -lt 3 ] || ([ "$python_major" -eq 3 ] && [ "$python_minor" -lt 11 ]); then
    echo "ERROR: Python 3.11+ is required (found $python_version)"
    exit 1
fi

# --- Detect package manager ---
if command -v uv &>/dev/null; then
    echo "uv:      $(uv --version)"
    PKG_MGR="uv"
else
    echo "uv:      not found (using pip instead)"
    PKG_MGR="pip"
fi

echo ""

# --- Create virtual environment ---
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    if [ "$PKG_MGR" = "uv" ]; then
        uv venv
    else
        python3 -m venv .venv
    fi
    echo "  -> .venv created"
else
    echo "Virtual environment already exists (.venv)"
fi

# --- Install dependencies ---
echo ""
echo "Installing dependencies..."
if [ "$PKG_MGR" = "uv" ]; then
    uv pip install -e ".[all]" --python .venv/bin/python
else
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -e ".[all]"
fi
echo "  -> Dependencies installed"

# --- Create default directories ---
echo ""
echo "Creating JARVIS directories..."
mkdir -p ~/.jarvis/{memory,sessions,skills,traces,logs,data,workflows}
echo "  -> ~/.jarvis/ directories created"

# --- Copy config files if not present ---
echo ""
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Created .env from .env.example"
        echo "  -> IMPORTANT: Edit .env to add your API keys"
    fi
else
    echo ".env already exists (skipping)"
fi

if [ ! -f "jarvis.yaml" ]; then
    if [ -f "jarvis.yaml.example" ]; then
        cp jarvis.yaml.example jarvis.yaml
        echo "Created jarvis.yaml from jarvis.yaml.example"
    fi
else
    echo "jarvis.yaml already exists (skipping)"
fi

# --- Run quick test suite ---
echo ""
echo "Running tests..."
test_output=$(.venv/bin/python -m pytest tests/ -q --tb=no 2>&1 | tail -3) || true
echo "$test_output"

# --- Done ---
echo ""
echo "-------------------------------------------"
echo "  JARVIS setup complete!"
echo "-------------------------------------------"
echo ""
echo "Next steps:"
echo "  1. Edit .env to add your API keys"
echo "  2. make run       - Start the server"
echo "  3. make run-tui   - Start the TUI"
echo "  4. make demo      - Run the demo"
echo "  5. Open http://localhost:8000"
echo ""
