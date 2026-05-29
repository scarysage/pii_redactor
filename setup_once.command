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
# 1. Find a usable Python in the 3.10 - 3.12 range.
# ----------------------------------------------------------------------------
# Why cap at 3.12: requirements.txt pins spaCy 3.7.5, which has prebuilt
# wheels for cp310 / cp311 / cp312 but NOT cp313. On Python 3.13 pip falls
# back to building thinc and spacy from source, which fails on most Macs
# without a full Cython/C toolchain set up. Forcing a known-good version
# range here is much friendlier than letting setup explode mid-install.
#
# Search order: most-preferred (3.12) first, falling back through versioned
# binaries Homebrew / python.org typically install. The plain `python3`
# symlink is checked last so a user who has multiple Pythons installed
# always gets the highest supported version, not whichever one happens to
# own the symlink today.
PY=""
PY_VERSION=""
for CAND in python3.12 python3.11 python3.10 python3; do
    if ! command -v "$CAND" >/dev/null 2>&1; then
        continue
    fi
    VER=$("$CAND" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null) || continue
    MAJ=${VER%.*}
    MIN=${VER#*.}
    if [ "$MAJ" = "3" ] && [ "$MIN" -ge 10 ] && [ "$MIN" -le 12 ]; then
        PY="$CAND"
        PY_VERSION="$VER"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "ERROR: No supported Python found on this Mac."
    echo
    echo "This tool needs Python 3.10, 3.11, or 3.12."
    echo "Python 3.13 (and newer) is NOT supported -- some required"
    echo "libraries do not have versions that work with 3.13 yet."
    echo
    echo "Install Python 3.12 from one of:"
    echo "  - python.org (recommended for non-developers):"
    echo "      https://www.python.org/downloads/release/python-3120/"
    echo "      Scroll down to 'macOS 64-bit universal2 installer' and run it."
    echo "  - Homebrew (if you already use it):"
    echo "      brew install python@3.12"
    echo
    echo "After installing, re-run setup_once.command."
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
