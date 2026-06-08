# =============================================================================
# JARVIS - Multi-stage Docker Build
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder - install dependencies and build the package
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build tools
RUN pip install --no-cache-dir uv

# Copy dependency spec first for layer caching
COPY pyproject.toml uv.lock* ./

# Install all dependencies (including optional)
RUN uv pip install --system -e ".[all]" || \
    uv pip install --system pydantic fastapi "uvicorn[standard]" typer pyyaml \
    sse-starlette rich httpx websockets openai anthropic

# Copy full source
COPY . .

# Install the package itself
RUN uv pip install --system -e .

# ---------------------------------------------------------------------------
# Stage 2: Runtime - minimal image for production
# ---------------------------------------------------------------------------
FROM python:3.12-slim

LABEL maintainer="JARVIS Project"
LABEL description="Streaming Spec driven personal AI assistant"

WORKDIR /app

# Install runtime system dependencies (curl for healthcheck fallback)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy the jarvis CLI entrypoint
COPY --from=builder /usr/local/bin/jarvis /usr/local/bin/

# Copy the application code
COPY --from=builder /app /app

# Create data directories
RUN mkdir -p /root/.jarvis/{memory,sessions,skills,traces,logs,data,workflows} && \
    mkdir -p /app/data

# Default environment
ENV JARVIS_LOG_LEVEL=INFO \
    JARVIS_LOG_FORMAT=human \
    JARVIS_HOST=0.0.0.0 \
    JARVIS_PORT=8000 \
    JARVIS_SANDBOX_MODE=basic

EXPOSE 8000

# Healthcheck using Python (httpx is already installed)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://localhost:8000/health'); assert r.status_code==200" \
    || curl -f http://localhost:8000/health || exit 1

# Run the server
CMD ["jarvis", "server", "start", "--host", "0.0.0.0"]
