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
REM 1. Find a usable Python in the 3.10 - 3.12 range.
REM ----------------------------------------------------------------------------
REM Why cap at 3.12: requirements.txt pins spaCy 3.7.5, which has prebuilt
REM wheels for cp310 / cp311 / cp312 but NOT cp313. On Python 3.13 pip falls
REM back to building thinc and spacy from source, which fails without a
REM full Visual C++ build toolchain installed. Forcing a known-good range
REM here is much friendlier than letting setup explode mid-install.
REM
REM Search order: prefer the Python launcher (`py -3.12`) because it
REM reliably picks a specific installed version. Falls back through 3.11,
REM 3.10, and finally a plain `python` (only if it happens to be in the
REM supported range).

SET "PY="
SET "PY_VERSION="

WHERE py >nul 2>&1
IF %ERRORLEVEL%==0 (
    py -3.12 -c "import sys" >nul 2>&1
    IF NOT ERRORLEVEL 1 (
        SET "PY=py -3.12"
        SET "PY_VERSION=3.12"
        GOTO :py_found
    )
    py -3.11 -c "import sys" >nul 2>&1
    IF NOT ERRORLEVEL 1 (
        SET "PY=py -3.11"
        SET "PY_VERSION=3.11"
        GOTO :py_found
    )
    py -3.10 -c "import sys" >nul 2>&1
    IF NOT ERRORLEVEL 1 (
        SET "PY=py -3.10"
        SET "PY_VERSION=3.10"
        GOTO :py_found
    )
)

REM Last-ditch: a plain `python` on PATH, but only if it's in the supported
REM range. We check version via a Python one-liner so we don't have to parse
REM `python --version` output ourselves.
WHERE python >nul 2>&1
IF %ERRORLEVEL%==0 (
    FOR /F "tokens=1,2 delims=." %%A IN ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') DO (
        SET "PY_MAJOR=%%A"
        SET "PY_MINOR=%%B"
    )
    IF "!PY_MAJOR!"=="3" (
        IF !PY_MINOR! GEQ 10 (
            IF !PY_MINOR! LEQ 12 (
                SET "PY=python"
                SET "PY_VERSION=!PY_MAJOR!.!PY_MINOR!"
                GOTO :py_found
            )
        )
    )
)

REM No usable Python found.
echo ERROR: No supported Python found on this PC.
echo.
echo This tool needs Python 3.10, 3.11, or 3.12.
echo Python 3.13 (and newer) is NOT supported -- some required
echo libraries do not have versions that work with 3.13 yet.
echo.
echo Install Python 3.12 from:
echo   https://www.python.org/downloads/release/python-3120/
echo Scroll down to "Windows installer (64-bit)" and run it.
echo.
echo IMPORTANT: when the installer opens, TICK the box that says
echo     "Add python.exe to PATH"
echo at the bottom of the FIRST screen, BEFORE clicking Install.
echo Without this checkbox, the tool will not find Python.
echo.
echo After installing, re-run setup_once.bat.
PAUSE
EXIT /B 1

:py_found
echo Using Python: %PY% (version %PY_VERSION%)

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
