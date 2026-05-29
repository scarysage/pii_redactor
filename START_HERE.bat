@echo off
REM ============================================================================
REM START_HERE.bat
REM
REM Day-to-day launcher. Activates the venv, starts Streamlit bound to
REM localhost, and opens the default browser to the app.
REM
REM Requires setup_once.bat to have been run first.
REM
REM NOTE: Windows-only. Has NOT been validated on a Windows VM yet -- per
REM CLAUDE.md, a Windows run is required before relying on this for
REM distribution.
REM ============================================================================

SETLOCAL ENABLEDELAYEDEXPANSION

REM Anchor to this script's directory regardless of CWD.
SET "SCRIPT_DIR=%~dp0"
PUSHD "%SCRIPT_DIR%"

IF NOT EXIST "%SCRIPT_DIR%.venv\Scripts\streamlit.exe" (
    echo ERROR: venv not found. Run setup_once.bat first.
    PAUSE
    EXIT /B 1
)

REM Open the browser once Streamlit is up. The /b flag avoids blocking.
START "" "http://127.0.0.1:8501"

REM Streamlit binds to 127.0.0.1 via .streamlit\config.toml -- the app is NOT
REM reachable from other machines on the network.
"%SCRIPT_DIR%.venv\Scripts\streamlit.exe" run "%SCRIPT_DIR%app.py"

POPD
ENDLOCAL
