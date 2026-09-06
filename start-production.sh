#!/usr/bin/env bash
# ==============================================================================
# DevPilot Production Launcher (Linux/macOS)
# Builds frontend assets and launches FastAPI production server
# ==============================================================================

set -e

echo "[1/3] Checking environment..."
if [ -d "venv" ]; then
    PYTHON_BIN="venv/bin/python"
    UVICORN_BIN="venv/bin/uvicorn"
elif [ -d ".venv" ]; then
    PYTHON_BIN=".venv/bin/python"
    UVICORN_BIN=".venv/bin/uvicorn"
else
    PYTHON_BIN="python3"
    UVICORN_BIN="uvicorn"
fi

echo "[2/3] Building frontend assets..."
cd frontend
npm ci || npm install
npm run build
cd ..

echo "[3/3] Starting DevPilot Production Server on http://0.0.0.0:8000 ..."
export DEVPILOT_ENV=production
export DEVPILOT_API_HOST=0.0.0.0
export DEVPILOT_API_PORT=8000

exec $UVICORN_BIN app.main:app --host 0.0.0.0 --port 8000
