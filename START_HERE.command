#!/bin/bash
# ============================================================================
# START_HERE.command  --  macOS launcher
#
# Day-to-day launcher. Activates the venv, starts Streamlit bound to
# localhost, and opens the default browser to the app.
#
# Requires setup_once.command to have been run first.
#
# On macOS, this is a double-clickable file. Finder will open Terminal
# automatically. To stop the app, close the Terminal window (or press
# Ctrl-C inside it).
# ============================================================================

set -e
set -u

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [ ! -f "$SCRIPT_DIR/.venv/bin/streamlit" ]; then
    echo "ERROR: venv not found. Run setup_once.command first."
    read -p "Press Enter to close..." _
    exit 1
fi

# Open the browser after a short delay so Streamlit has time to bind 8501.
# The & runs it in the background; the parent shell keeps going.
( sleep 2 && open "http://127.0.0.1:8501" ) &

# Streamlit binds to 127.0.0.1 via .streamlit/config.toml -- the app is NOT
# reachable from other machines on the network.
"$SCRIPT_DIR/.venv/bin/streamlit" run "$SCRIPT_DIR/app.py"
