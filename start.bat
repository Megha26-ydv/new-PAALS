@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   PAALS — Supply Chain Oversight Platform
echo ============================================================
echo.

:: ── Check Python availability ────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ from:
    echo         https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% detected

:: ── Create virtual environment if missing ────────────────────────────────────
if not exist ".venv" (
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

:: ── Activate virtual environment ─────────────────────────────────────────────
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
echo [OK] Virtual environment activated

:: ── Upgrade pip silently ─────────────────────────────────────────────────────
echo [SETUP] Upgrading pip...
python -m pip install --upgrade pip --quiet

:: ── Install dependencies ─────────────────────────────────────────────────────
echo [SETUP] Installing dependencies from requirements.txt...
echo         (This may take 2-3 minutes on first run)
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    echo         Try running manually: pip install -r requirements.txt
    pause
    exit /b 1
)
echo [OK] All dependencies installed

:: ── Create database directory if missing ─────────────────────────────────────
if not exist "database" (
    mkdir database
    echo [OK] database/ directory created
)

:: ── Check for .env file ──────────────────────────────────────────────────────
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] .env created from .env.example
    )
)

:: ── Start the server ─────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Starting PAALS server...
echo   Database will be seeded on first run (~5 seconds)
echo ============================================================
echo.
echo   Dashboard:       http://127.0.0.1:8000
echo   Deviations:      http://127.0.0.1:8000/deviations
echo   Action Centre:   http://127.0.0.1:8000/action-centre
echo   Suppliers:       http://127.0.0.1:8000/suppliers
echo   Purchase Orders: http://127.0.0.1:8000/purchase-orders
echo   Digital Twin:    http://127.0.0.1:8000/digital-twin
echo   Research:        http://127.0.0.1:8000/research
echo   API Docs:        http://127.0.0.1:8000/docs
echo.
echo   Press Ctrl+C to stop the server.
echo ============================================================
echo.

python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

:: ── Handle exit ──────────────────────────────────────────────────────────────
echo.
echo Server stopped.
pause
