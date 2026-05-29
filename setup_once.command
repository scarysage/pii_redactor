#!/bin/bash
# ============================================================================
# setup_once.command  --  macOS one-time setup
#
# Mac equivalent of setup_once.bat. Run this once after unzipping the tool to
# its permanent location (e.g. ~/Applications/pii-redactor/). Re-running is
# safe -- it detects an existing venv and skips the heavy steps.
#
# IMPORTANT for first-time users:
#   * Move the unzipped pii-redactor folder to a permanent location FIRST
#     (~/Applications/pii-redactor/ or ~/Documents/pii-redactor/), then run
#     this from there. Do NOT run from Downloads or any temp folder.
#   * macOS Gatekeeper may block this on the first double-click ("cannot be
#     opened because the developer cannot be verified"). Right-click the
#     file, choose Open, then click Open in the dialog. After that, normal
#     double-click works.
#   * This script does NOT phone home for the spaCy model. The model is
#     vendored in the en_core_web_lg/ folder shipped inside the zip.
#     If that folder is missing, the zip is incomplete -- stop and
#     re-download. Do NOT add a `spacy download` step here.
# ============================================================================

set -e  # exit on first error
set -u  # error on undefined vars

# Anchor every path to THIS script's location, not the CWD.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo
echo "=== pii-redactor setup ==="
echo "Working dir: $SCRIPT_DIR"
echo

# ----------------------------------------------------------------------------
# 1. Find a usable Python 3. We do NOT bundle Python; users install it once.
# ----------------------------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
    PY=python3
else
    echo "ERROR: python3 is not installed or not on PATH."
    echo
    echo "Install Python 3.10+ from one of:"
    echo "  - https://www.python.org/downloads/  (official installer)"
    echo "  - Homebrew: brew install python@3.12"
    echo
    echo "Then re-run setup_once.command."
    read -p "Press Enter to close..." _
    exit 1
fi

# Minimal version check: need Python 3.10+ for the requirements pins.
PY_VERSION=$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=${PY_VERSION%.*}
PY_MINOR=${PY_VERSION#*.}
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "ERROR: Python $PY_VERSION found, but 3.10 or newer is required."
    echo "Install a newer Python and re-run."
    read -p "Press Enter to close..." _
    exit 1
fi
echo "Using Python: $PY ($PY_VERSION)"

# ----------------------------------------------------------------------------
# 2. Verify the vendored spaCy model is present. If not, abort -- do not
#    attempt to download.
# ----------------------------------------------------------------------------
if [ ! -f "$SCRIPT_DIR/en_core_web_lg/config.cfg" ]; then
    echo "ERROR: Vendored spaCy model is missing."
    echo "Expected: $SCRIPT_DIR/en_core_web_lg/config.cfg"
    echo
    echo "The zip is incomplete. Re-download it. Do NOT try to fix this by"
    echo "running 'python -m spacy download' -- this tool is offline-only."
    read -p "Press Enter to close..." _
    exit 1
fi

# ----------------------------------------------------------------------------
# 3. Create the venv (if not already there) and install requirements.
# ----------------------------------------------------------------------------
if [ ! -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    echo "Creating venv..."
    "$PY" -m venv "$SCRIPT_DIR/.venv"
else
    echo "venv already exists -- skipping creation."
fi

echo "Installing requirements (this may take a few minutes the first time)..."
"$SCRIPT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$SCRIPT_DIR/.venv/bin/python" -m pip install -r "$SCRIPT_DIR/requirements.txt"

echo
echo "=== Setup complete ==="
echo "You can now use START_HERE.command to launch the redactor."
echo
read -p "Press Enter to close..." _
