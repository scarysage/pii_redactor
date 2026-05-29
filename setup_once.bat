@echo off
REM ============================================================================
REM setup_once.bat
REM
REM One-time setup, per PC. Run this once after unzipping the tool to its
REM permanent location (e.g. C:\pii-redactor\). Re-running is safe -- it will
REM detect an existing venv and skip the heavy steps.
REM
REM IMPORTANT for the IT person:
REM   * Do NOT run this from Downloads or a temp folder. Move the unzipped
REM     pii-redactor folder to a permanent location FIRST (C:\pii-redactor\
REM     is the recommended path), then run setup_once.bat from there.
REM   * Mark of the Web: Windows may block .bat files that came from a
REM     downloaded zip. If the script refuses to run, right-click the .bat,
REM     Properties, and tick "Unblock" at the bottom. See RUNBOOK.md.
REM   * This script does NOT phone home for the spaCy model. The model is
REM     vendored in the en_core_web_lg\ folder shipped inside the zip.
REM     If that folder is missing, the zip is incomplete -- stop and
REM     re-download. Do NOT add a `spacy download` step.
REM
REM NOTE: this file is Windows-only and has NOT been validated on a Windows
REM VM yet -- per CLAUDE.md packaging test gate, a Windows run is required
REM before relying on it for distribution.
REM ============================================================================

SETLOCAL ENABLEDELAYEDEXPANSION

REM Anchor every path to THIS script's location, not the CWD. Users run the
REM .bat by double-clicking, so CWD may be anything.
SET "SCRIPT_DIR=%~dp0"
PUSHD "%SCRIPT_DIR%"

echo.
echo === pii-redactor setup ===
echo Working dir: %CD%
echo.

REM ----------------------------------------------------------------------------
REM 1. Find a usable Python. We do NOT bundle Python; users install it once.
REM ----------------------------------------------------------------------------
WHERE py >nul 2>&1
IF %ERRORLEVEL%==0 (
    SET "PY=py -3"
) ELSE (
    WHERE python >nul 2>&1
    IF %ERRORLEVEL%==0 (
        SET "PY=python"
    ) ELSE (
        echo ERROR: Python is not installed or not on PATH.
        echo Install Python 3.10+ from https://www.python.org/downloads/
        echo Re-run setup_once.bat after installing.
        PAUSE
        EXIT /B 1
    )
)
echo Using Python: %PY%

REM ----------------------------------------------------------------------------
REM 2. Verify the vendored spaCy model is present. If not, abort -- do not
REM    attempt to download.
REM ----------------------------------------------------------------------------
IF NOT EXIST "%SCRIPT_DIR%en_core_web_lg\config.cfg" (
    echo ERROR: Vendored spaCy model is missing.
    echo Expected: %SCRIPT_DIR%en_core_web_lg\config.cfg
    echo The zip is incomplete. Re-download it; do NOT try to fix this by
    echo running `python -m spacy download` -- this tool is offline-only.
    PAUSE
    EXIT /B 1
)

REM ----------------------------------------------------------------------------
REM 3. Create the venv (if not already there) and install requirements.
REM ----------------------------------------------------------------------------
IF NOT EXIST "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    echo Creating venv...
    %PY% -m venv "%SCRIPT_DIR%.venv"
    IF ERRORLEVEL 1 (
        echo ERROR: Could not create venv.
        PAUSE
        EXIT /B 1
    )
) ELSE (
    echo venv already exists -- skipping creation.
)

echo Installing requirements (this may take a few minutes the first time)...
"%SCRIPT_DIR%.venv\Scripts\python.exe" -m pip install --upgrade pip
"%SCRIPT_DIR%.venv\Scripts\python.exe" -m pip install -r "%SCRIPT_DIR%requirements.txt"
IF ERRORLEVEL 1 (
    echo ERROR: pip install failed.
    PAUSE
    EXIT /B 1
)

echo.
echo === Setup complete ===
echo You can now use START_HERE.bat to launch the redactor.
echo.

POPD
ENDLOCAL
PAUSE
