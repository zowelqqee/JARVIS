@echo off
setlocal EnableDelayedExpansion
title JARVIS Build

echo.
echo  ================================================
echo   J.A.R.V.I.S  -  PyInstaller Build  (onedir)
echo  ================================================
echo.

:: ── Change to script's own directory ──────────────────────────────────────
cd /d "%~dp0"

:: ── Activate virtual environment (try .venv first, then venv) ─────────────
if exist ".venv\Scripts\activate.bat" (
    echo [build] Activating .venv ...
    call ".venv\Scripts\activate.bat"
    goto :check_pyinstaller
)
if exist "venv\Scripts\activate.bat" (
    echo [build] Activating venv ...
    call "venv\Scripts\activate.bat"
    goto :check_pyinstaller
)
echo [build] No venv found — using system Python.

:check_pyinstaller
:: ── Ensure PyInstaller is installed ───────────────────────────────────────
python -m pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [build] PyInstaller not found — installing ...
    pip install pyinstaller
    if errorlevel 1 (
        echo [build] ERROR: pip install pyinstaller failed.
        pause
        exit /b 1
    )
)

:: ── Run the build ─────────────────────────────────────────────────────────
echo.
echo [build] Running PyInstaller (this may take a few minutes) ...
echo.
python -m pyinstaller jarvis.spec --clean

if errorlevel 1 (
    echo.
    echo  ================================================
    echo   BUILD FAILED — see output above for details.
    echo  ================================================
    echo.
    pause
    exit /b 1
)

:: ── Post-build: install Playwright browsers ────────────────────────────────
echo.
echo [build] Installing Playwright browser binaries ...
echo         (required for browser_control — downloads ~200 MB)
echo.
python -m playwright install chromium
if errorlevel 1 (
    echo [build] WARNING: Playwright browser install failed.
    echo         Run manually on the target machine:
    echo           python -m playwright install chromium
)

:: ── Success ───────────────────────────────────────────────────────────────
echo.
echo  ================================================
echo   BUILD COMPLETE  ->  dist\JARVIS\
echo  ================================================
echo.
echo  Distribution checklist:
echo    [OK]  dist\JARVIS\JARVIS.exe
echo    [OK]  dist\JARVIS\face.png  (bundled)
echo    [OK]  dist\JARVIS\core\prompt.txt  (bundled)
echo    [ ]   dist\JARVIS\config\api_keys.json  (written on first launch)
echo    [ ]   Playwright browsers installed on target  (playwright install chromium)
echo.
echo [build] Opening dist\JARVIS\ in Explorer ...
explorer "dist\JARVIS"

endlocal
