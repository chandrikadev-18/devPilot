@echo off
REM ==============================================================================
REM DevPilot Production Launcher (Windows)
REM Builds frontend assets and launches FastAPI production server
REM ==============================================================================

echo [1/3] Checking environment...
if not exist "venv\Scripts\python.exe" (
    echo Error: Python virtual environment not found in .\venv.
    echo Please create it with 'python -m venv venv' and run 'pip install -r requirements.txt'.
    exit /b 1
)

echo [2/3] Building frontend assets...
cd frontend
call npm install
if %ERRORLEVEL% NEQ 0 (
    echo Error: npm install failed.
    cd ..
    exit /b 1
)
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo Error: Frontend build failed.
    cd ..
    exit /b 1
)
cd ..

echo [3/3] Starting DevPilot Production Server on http://0.0.0.0:8000 ...
set DEVPILOT_ENV=production
set DEVPILOT_API_HOST=0.0.0.0
set DEVPILOT_API_PORT=8000
.\venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000
