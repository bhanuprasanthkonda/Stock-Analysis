@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: start.bat — Local Stock Analyzer launcher (Windows)
::
:: First run:  automatically installs all dependencies then starts the app.
:: Later runs: skips install, starts immediately.
::
:: Requires: Python 3.10+ and Node.js 18+ to be installed.
:: ─────────────────────────────────────────────────────────────────────────────
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ================================================
echo   Local Stock Analyzer
echo ================================================
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: python not found.
    echo Install Python 3.10+ from https://python.org
    echo Make sure to check "Add Python to PATH" during install.
    pause & exit /b 1
)

:: ── Check Node ───────────────────────────────────────────────────────────────
where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: node not found.
    echo Install Node.js 18+ from https://nodejs.org
    pause & exit /b 1
)

:: ── Backend: create venv if missing ──────────────────────────────────────────
if not exist "backend\venv" (
    echo [1/4] Creating Python virtual environment...
    python -m venv backend\venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause & exit /b 1
    )
)

:: ── Backend: install packages ─────────────────────────────────────────────────
if not exist "backend\venv\.install_stamp" (
    echo [2/4] Installing backend packages...
    call backend\venv\Scripts\activate.bat
    python -m pip install --quiet --upgrade pip
    pip install --quiet -r backend\requirements.txt
    if errorlevel 1 (
        echo ERROR: pip install failed.
        pause & exit /b 1
    )
    echo. > backend\venv\.install_stamp
) else (
    echo [2/4] Backend packages up to date.
)

:: ── Frontend: always run npm install so new packages are picked up ───────────
:: npm install is fast when nothing changed; package-lock.json pins exact
:: versions for reproducible installs across machines.
echo [3/4] Checking frontend packages...
cd frontend
npm install
if errorlevel 1 (
    echo ERROR: npm install failed.
    cd ..
    pause & exit /b 1
)
cd ..

echo [4/4] Starting servers...
echo.

:: ── Start backend in its own window ──────────────────────────────────────────
start "Stock Analyzer - Backend" cmd /k "cd /d "%~dp0backend" && venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

:: ── Wait for backend to initialise ───────────────────────────────────────────
timeout /t 5 /nobreak >nul

:: ── Start frontend in its own window ─────────────────────────────────────────
start "Stock Analyzer - Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

:: ── Wait for Vite to start ────────────────────────────────────────────────────
timeout /t 5 /nobreak >nul

:: ── Open the browser ──────────────────────────────────────────────────────────
start http://localhost:5173

echo   Backend  -^>  http://localhost:8000
echo   API docs -^>  http://localhost:8000/docs
echo   Frontend -^>  http://localhost:5173
echo.
echo   Close the Backend and Frontend windows to stop the servers.
echo.
pause
