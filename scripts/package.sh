#!/bin/bash
# ============================================================================
# scripts/package.sh
#
# Build a clean distribution zip of the pii-redactor for handoff to a Mac
# or Windows test machine.
#
# Run from anywhere; the script anchors to the repo root.
#
# What goes in:
#   * All source files (.py, .bat, .command, .md, .toml, .txt, etc.)
#   * The vendored spaCy model (en_core_web_lg/)
#   * The .streamlit config
#   * The tests/ directory (small; useful to have on the target machine)
#
# What stays out:
#   * .venv/        -- rebuilt by setup_once on the target machine
#   * .git/         -- not needed at runtime
#   * __pycache__/  -- bytecode caches
#   * .pytest_cache/, .ruff_cache/, .claude/
#   * user_additions.txt -- per-installation; shipping yours would clobber
#     the target user's own saved entries
#
# Output: ../pii-redactor-<timestamp>.zip (one directory UP from the repo
# root, so subsequent runs don't sweep an old zip into the new one).
# ============================================================================

set -e
set -u

# Anchor to the REPO ROOT (one level up from scripts/).
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
REPO_NAME="$( basename "$REPO_ROOT" )"
PARENT_DIR="$( cd "$REPO_ROOT/.." && pwd )"

TIMESTAMP="$( date +%Y%m%d-%H%M )"
OUT="$PARENT_DIR/pii-redactor-$TIMESTAMP.zip"

echo "Repo root:  $REPO_ROOT"
echo "Output zip: $OUT"
echo

# Sanity: the model must be vendored, otherwise the zip will fail on the
# target machine with a clear "model missing" error. Catch it now instead.
if [ ! -f "$REPO_ROOT/en_core_web_lg/config.cfg" ]; then
    echo "ERROR: en_core_web_lg/config.cfg is missing in $REPO_ROOT."
    echo "Run: .venv/bin/python scripts/vendor_model.py"
    exit 1
fi

# Build the zip from the PARENT dir so paths inside the archive begin with
# the repo folder name (so unzip creates pii_redactor/, not loose files).
cd "$PARENT_DIR"

# `zip -x` takes glob patterns relative to the working dir, hence the
# REPO_NAME/ prefixes.
zip -r -q "$OUT" "$REPO_NAME" \
    -x "$REPO_NAME/.venv/*" \
       "$REPO_NAME/.git/*" \
       "$REPO_NAME/.gitignore" \
       "$REPO_NAME/.claude/*" \
       "$REPO_NAME/.pytest_cache/*" \
       "$REPO_NAME/.ruff_cache/*" \
       "$REPO_NAME/__pycache__/*" \
       "$REPO_NAME/*/__pycache__/*" \
       "$REPO_NAME/*/*/__pycache__/*" \
       "$REPO_NAME/user_additions.txt" \
       "$REPO_NAME/*.zip"

# Post-build verification: spot-check that critical files are present.
echo
echo "=== Verifying archive contents ==="
REQUIRED=(
    "$REPO_NAME/app.py"
    "$REPO_NAME/redactor.py"
    "$REPO_NAME/recognizers.py"
    "$REPO_NAME/extractors.py"
    "$REPO_NAME/firm_config.py"
    "$REPO_NAME/user_additions.py"
    "$REPO_NAME/requirements.txt"
    "$REPO_NAME/setup_once.command"
    "$REPO_NAME/START_HERE.command"
    "$REPO_NAME/setup_once.bat"
    "$REPO_NAME/START_HERE.bat"
    "$REPO_NAME/en_core_web_lg/config.cfg"
    "$REPO_NAME/.streamlit/config.toml"
    "$REPO_NAME/LICENSE"
    "$REPO_NAME/THIRD_PARTY_LICENSES.md"
)
MISSING=0
for f in "${REQUIRED[@]}"; do
    if ! unzip -l "$OUT" "$f" >/dev/null 2>&1; then
        echo "  [MISSING] $f"
        MISSING=$((MISSING + 1))
    fi
done

if [ $MISSING -gt 0 ]; then
    echo
    echo "ERROR: $MISSING required file(s) missing from the archive."
    exit 1
fi

# Belt and braces: confirm .venv did NOT get swept in.
if unzip -l "$OUT" "$REPO_NAME/.venv/*" >/dev/null 2>&1; then
    echo "ERROR: .venv/ leaked into the archive."
    exit 1
fi

# Confirm user_additions.txt is absent (don't want to clobber the target).
if unzip -l "$OUT" "$REPO_NAME/user_additions.txt" >/dev/null 2>&1; then
    echo "ERROR: user_additions.txt leaked into the archive."
    exit 1
fi

SIZE=$( du -h "$OUT" | cut -f1 )
FILECOUNT=$( unzip -l "$OUT" | tail -1 | awk '{ print $2 }' )
echo "All required files present."
echo
echo "=== Done ==="
echo "Zip:   $OUT"
echo "Size:  $SIZE"
echo "Files: $FILECOUNT"
