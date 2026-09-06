# ==============================================================================
# Multi-Stage Dockerfile for DevPilot (Fullstack Production Build)
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build Frontend (Vite + React + TypeScript)
# ------------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder
WORKDIR /build

# Install dependencies
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy source code and build production assets
COPY frontend/ ./
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Python Backend Runtime
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Install system utilities & build tools (required for tree-sitter & Git integration)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Set production environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEVPILOT_ENV=production \
    DEVPILOT_API_HOST=0.0.0.0 \
    DEVPILOT_API_PORT=8000 \
    ALLOWED_ORIGINS="*"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend codebase
COPY app/ ./app/
COPY conftest.py pytest.ini ./
COPY data/ ./data/

# Copy built frontend distribution from builder stage
COPY --from=frontend-builder /build/dist ./frontend/dist

# Create storage directory for devpilot metadata
RUN mkdir -p /app/.devpilot /app/data

# Expose API and frontend port
EXPOSE 8000

# Container Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start production uvicorn server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
