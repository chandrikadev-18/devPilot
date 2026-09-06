# DevPilot Production Deployment Guide 🚀

This document outlines how to deploy **DevPilot** (Fullstack AI Codebase Exploration, RAG, and Autonomous Change Engine) to production environments.

---

## Architecture Overview

DevPilot is comprised of:
1. **Backend API (FastAPI)**: REST endpoints for parsing, indexer, vector search (Qdrant), RAG pipeline, Git intelligence, call graph analysis, and AI codebase agents.
2. **Frontend (React + Vite + TypeScript)**: Interactive UI for dashboards, graph visualizer, semantic search, AI agent interface, and project management.
3. **Storage & Embeddings**:
   - Vector database engine (`qdrant-client`)
   - Local embeddings with `sentence-transformers` (`all-MiniLM-L6-v2`)
   - Metadata persistence in `.devpilot/`

In production, DevPilot can be deployed:
- **Option A (Unified Single Service)**: FastAPI serves the compiled React frontend directly on port 8000.
- **Option B (Docker / Docker Compose)**: Containerized deployment ready for Docker, Kubernetes, or container clouds.
- **Option C (Decoupled Cloud)**: Frontend on Vercel/Netlify/Cloudflare Pages + Backend on Render/Railway/Fly.io/AWS.

---

## 1. Quick Local Production Run (1-Click)

### On Windows
```cmd
start-production.bat
```

### On Linux / macOS
```bash
chmod +x start-production.sh
./start-production.sh
```

This will:
1. Build frontend distribution assets (`frontend/dist`)
2. Start the FastAPI server on `http://0.0.0.0:8000`
3. Serve both API (`/api/v1/...`, `/health`, `/projects`, `/changes`) and the React SPA on `http://localhost:8000`.

---

## 2. Docker Deployment

### Building and Running the Docker Image

```bash
# 1. Build the multi-stage production image
docker build -t devpilot:latest .

# 2. Run the container with persistent storage
docker run -d \
  -p 8000:8000 \
  --name devpilot \
  -e LLM_API_KEY="your-api-key-here" \
  -e GROQ_API_KEY="your-groq-api-key-here" \
  -e DEVPILOT_ENV="production" \
  -v devpilot_data:/app/.devpilot \
  -v devpilot_storage:/app/data \
  devpilot:latest
```

### Using Docker Compose

```bash
# 1. Configure environment variables in .env
cp .env.example .env
# Edit .env with your LLM_API_KEY / GROQ_API_KEY

# 2. Start services in background
docker compose up -d

# 3. Check logs
docker compose logs -f

# 4. Stop services
docker compose down
```

---

## 3. Cloud Deployment Options

### Deploying to Render / Railway / Fly.io

1. **Connect GitHub Repository** to Render / Railway / Fly.io.
2. **Select Dockerfile deployment** (Render and Railway detect `Dockerfile` automatically).
3. **Environment Variables**:
   ```ini
   DEVPILOT_ENV=production
   LLM_PROVIDER=groq
   GROQ_API_KEY=gsk_your_groq_key
   ALLOWED_ORIGINS=*
   PORT=8000
   ```
4. **Persistent Disk (Optional but recommended)**:
   - Mount disk to `/app/.devpilot` and `/app/data` (1-5 GB is sufficient).
5. **Health Check Path**: `/health`

---

### Deploying on Linux Virtual Server (Ubuntu / Debian VPS)

```bash
# 1. Clone repository
git clone <your-repo-url> /opt/devpilot
cd /opt/devpilot

# 2. Setup Python virtual environment
sudo apt-get update && sudo apt-get install -y python3-venv python3-pip git build-essential nodejs npm
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 3. Build frontend
cd frontend
npm ci
npm run build
cd ..

# 4. Setup Systemd Service (/etc/systemd/system/devpilot.service)
sudo tee /etc/systemd/system/devpilot.service << 'EOF'
[Unit]
Description=DevPilot Production API & UI
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/devpilot
EnvironmentFile=/opt/devpilot/.env
ExecStart=/opt/devpilot/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 5. Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable devpilot
sudo systemctl start devpilot
```

---

## 4. Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `DEVPILOT_ENV` | `development` | Environment mode (`development`, `production`, `test`) |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `DEVPILOT_API_HOST` | `127.0.0.1` | Host to bind API server (use `0.0.0.0` in Docker/cloud) |
| `DEVPILOT_API_PORT` | `8000` | Port for the API server |
| `ALLOWED_ORIGINS` | `*` or localhost | Comma-separated list of allowed CORS origins or `*` |
| `LLM_PROVIDER` | `groq` | LLM backend provider (`groq`, `openai`, etc.) |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Model name for completions and reasoning |
| `LLM_API_KEY` | None | General LLM API key |
| `GROQ_API_KEY` | None | Groq-specific API key |
| `MAX_PROJECT_SIZE_MB` | `500.0` | Maximum scanned project size in MB |
| `OPERATION_TIMEOUT` | `60.0` | Timeout in seconds for indexing & graph builds |

---

## 5. Production Health & Observability

- **Liveness probe**: `GET /health` (Returns HTTP 200 `{"status": "ok"}`)
- **Detailed system health**: `GET /health/details` (Returns vector store, LLM provider, disk, and configuration health)
- **API Documentation**: `GET /docs` (Interactive OpenAPI Swagger UI)
