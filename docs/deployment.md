# JARVIS Deployment Guide

This guide covers local development, Docker deployment, and production considerations.

---

## Table of Contents

1. [Local Development](#local-development)
2. [Docker Deployment](#docker-deployment)
3. [Docker Compose Profiles](#docker-compose-profiles)
4. [Environment Variables](#environment-variables)
5. [Configuration](#configuration)
6. [Health Checks](#health-checks)
7. [Monitoring](#monitoring)
8. [Production Checklist](#production-checklist)

---

## Local Development

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Git

### Quick Start

```bash
# Clone and install
git clone <repo-url> jarvis && cd jarvis
uv sync                          # creates .venv and installs all deps

# Or with make:
make install                     # install runtime deps
make dev                         # install runtime + dev deps (pytest, ruff, mypy)

# Configure (optional -- JARVIS works without API keys in mock mode)
cp .env.example .env
# Edit .env to add your OPENAI_API_KEY or ANTHROPIC_API_KEY
```

### Running

```bash
# Start the FastAPI server (with hot reload)
make run
# Server is at http://127.0.0.1:8000
# API docs at http://127.0.0.1:8000/docs

# Run the interactive demo
make demo

# Start the TUI (terminal user interface)
make run-tui

# Open a Python shell with JARVIS loaded
make shell
```

### Development Workflow

```bash
# Run tests
make test                        # full suite
make test-fast                   # skip slow tests
make test-coverage               # with coverage report

# Code quality
make lint                        # ruff check
make format                      # ruff format
make typecheck                   # mypy
make check                       # lint + typecheck

# Benchmarks
make benchmark                   # quick benchmark (50 iterations)
make benchmark-full              # full benchmark suite

# Project statistics
make stats                       # LOC, file counts, etc.
```

---

## Docker Deployment

### Building the Image

```bash
# Build using the multi-stage Dockerfile
docker build -t jarvis:latest .

# Or using make:
make docker-build
```

The Dockerfile uses a two-stage build:
1. **Builder stage** -- installs dependencies with uv
2. **Runtime stage** -- minimal `python:3.12-slim` image with only runtime dependencies

### Running with Docker

```bash
# Run standalone
docker run -d \
  --name jarvis \
  -p 8000:8000 \
  -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
  -v jarvis-data:/app/data \
  -v jarvis-memory:/root/.jarvis \
  jarvis:latest

# Check health
curl http://localhost:8000/health
```

### Data Volumes

| Volume | Path in Container | Purpose |
|--------|-------------------|---------|
| `jarvis-data` | `/app/data` | Application data (specs, logs) |
| `jarvis-memory` | `/root/.jarvis` | Persistent memory, sessions, skills, traces |

---

## Docker Compose Profiles

The `docker-compose.yml` defines three profiles:

### Basic (default)

```bash
docker compose up -d
```

Starts only the JARVIS server. Uses in-memory storage and no external services.

### Full (Redis + PostgreSQL)

```bash
docker compose --profile full up -d
```

Adds:
- **Redis 7** -- caching and pub/sub (port 6379)
  - Memory limit: 256MB with LRU eviction
  - Append-only file persistence
- **PostgreSQL 16** -- persistent storage (port 5432)
  - Database: `jarvis`, User: `jarvis`
  - Set `POSTGRES_PASSWORD` in `.env`

### Local LLM (Ollama)

```bash
docker compose --profile local-llm up -d
```

Adds:
- **Ollama** -- local LLM inference (port 11434)
  - GPU support (NVIDIA) via Docker GPU passthrough
  - Models stored in `ollama-data` volume

### Everything

```bash
docker compose --profile full --profile local-llm up -d
```

### Stopping

```bash
# Stop containers (preserve data)
docker compose down

# Stop and remove all data volumes
docker compose down -v
```

### Useful Commands

```bash
# View logs
docker compose logs -f jarvis

# Shell into the container
docker compose exec jarvis /bin/bash

# Rebuild after code changes
docker compose build jarvis
docker compose up -d jarvis
```

---

## Environment Variables

All environment variables can be set in `.env` or passed directly:

### LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `JARVIS_DEFAULT_MODEL` | `gpt-4o-mini` | Default LLM model name |
| `OPENAI_API_KEY` | (empty) | OpenAI API key |
| `ANTHROPIC_API_KEY` | (empty) | Anthropic API key |
| `DEEPSEEK_API_KEY` | (empty) | DeepSeek API key |

If no API keys are set, JARVIS runs in mock mode with deterministic fallbacks.

### Server

| Variable | Default | Description |
|----------|---------|-------------|
| `JARVIS_HOST` | `127.0.0.1` | Server bind address |
| `JARVIS_PORT` | `8000` | Server port |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `JARVIS_SANDBOX_MODE` | `basic` | Sandbox mode: `none`, `basic`, `strict`, `docker` |
| `JARVIS_SECRET_SCANNING` | `true` | Enable secret detection in outputs |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `JARVIS_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `JARVIS_LOG_FORMAT` | `human` | Log format: `human` or `json` |

### Database (Full profile)

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_PASSWORD` | `jarvis_dev` | PostgreSQL password |
| `DATABASE_URL` | (empty) | PostgreSQL connection string |
| `REDIS_URL` | (empty) | Redis connection string |

---

## Configuration

### jarvis.yaml

The primary configuration file is `jarvis.yaml` at the project root:

```yaml
app_name: JARVIS
version: 0.2.0
specs_dir: specs

log:
  level: INFO
  format: "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
  file: ""                     # empty = stderr only

server:
  host: 127.0.0.1
  port: 8000
  reload: true
  cors_origins:
    - "http://localhost:8000"

agents:
  enabled_agents:
    - code-agent
    - calendar-agent
    - knowledge-agent
    - comms-agent
    - ops-agent
  default_model: claude-sonnet-4-6
  max_concurrent: 5
  timeout: 120                 # seconds per agent call

security:
  sandbox_mode: basic
  secret_scanning: true
  allowed_domains: []

streaming_spec:
  enabled: true
  checkpoint_interval: 5      # seconds between auto-saves
  max_history: 100

storage:
  backend: local
  data_dir: data
  memory_dir: ~/.jarvis
```

### Data Directories

| Directory | Purpose |
|-----------|---------|
| `~/.jarvis/memory/` | Persistent memory entries |
| `~/.jarvis/sessions/` | Session history |
| `~/.jarvis/skills/` | Skill YAML files and execution history |
| `~/.jarvis/traces/` | Trace JSON files |
| `~/.jarvis/logs/` | Log files (if file logging is enabled) |
| `~/.jarvis/data/` | Key-value store data |
| `~/.jarvis/workflows/` | Workflow state |
| `data/` | Application data (relative to project root) |
| `specs/` | YAML spec templates |
| `skills/` | Bundled skill definitions |

---

## Health Checks

### HTTP Health Endpoint

```bash
curl http://localhost:8000/health
```

Response:

```json
{
  "status": "ok",
  "agents": 10,
  "specs": 0,
  "agent_specs": 5
}
```

### Docker Health Check

The Dockerfile includes a built-in health check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://localhost:8000/health'); assert r.status_code==200"
```

Check health status:

```bash
docker inspect --format='{{.State.Health.Status}}' jarvis-server
```

### Docker Compose Health Checks

All services in `docker-compose.yml` have health checks:
- **JARVIS** -- HTTP GET `/health` every 30s
- **Redis** -- `redis-cli ping` every 10s
- **PostgreSQL** -- `pg_isready -U jarvis` every 10s

---

## Monitoring

### Metrics Endpoint

```bash
curl http://localhost:8000/metrics
```

Returns counters, histograms (with percentiles), and gauges for all system operations.

### Traces Endpoint

```bash
# List recent traces
curl http://localhost:8000/traces

# Get a specific trace
curl http://localhost:8000/traces/{trace_id}
```

### System Info

```bash
curl http://localhost:8000/system
```

Returns version, module status, agent count, tool count, and active spec count.

### Diagnostics

```bash
# From the CLI
make diagnostics

# Programmatic
python -c "
import asyncio
from jarvis.diagnostics import SystemDiagnostics
d = SystemDiagnostics()
r = asyncio.run(d.run_all())
print(r.to_table())
"
```

### Log Aggregation

For structured JSON logging (suitable for log aggregation tools):

```bash
JARVIS_LOG_FORMAT=json make run
```

---

## Production Checklist

### Security

- [ ] Set `JARVIS_SANDBOX_MODE=strict` (or `docker` for containerized tool execution)
- [ ] Enable `JARVIS_SECRET_SCANNING=true`
- [ ] Restrict `cors_origins` in `jarvis.yaml` to your domain
- [ ] Add API key authentication (custom middleware) before exposing to the internet
- [ ] Review and restrict the sandbox `allowed_commands` list
- [ ] Ensure `.env` file is not committed to version control

### Infrastructure

- [ ] Use the `full` Docker Compose profile for Redis + PostgreSQL
- [ ] Configure persistent volumes for `/app/data` and `/root/.jarvis`
- [ ] Set up a reverse proxy (nginx/Caddy) with TLS termination
- [ ] Configure log rotation for file logging
- [ ] Set appropriate resource limits (CPU, memory) in Docker

### Monitoring

- [ ] Set up health check monitoring (uptime alerts)
- [ ] Configure log aggregation (ELK, Datadog, etc.)
- [ ] Set up metric dashboards from the `/metrics` endpoint
- [ ] Configure alerting on error rate spikes
- [ ] Monitor disk usage for trace and event storage

### Performance

- [ ] Set `JARVIS_LOG_LEVEL=WARNING` for production (reduce log volume)
- [ ] Configure agent `max_concurrent` based on available resources
- [ ] Set appropriate rate limits in the Gateway configuration
- [ ] Consider running Ollama on a dedicated GPU node for local LLM inference
- [ ] Tune PostgreSQL connection pool size if using the full profile

### Backup

- [ ] Back up `~/.jarvis/` directory (memory, sessions, skills, traces)
- [ ] Back up PostgreSQL database (if using full profile)
- [ ] Back up `skills/` directory (custom skill definitions)
- [ ] Back up `specs/` directory (spec templates)
