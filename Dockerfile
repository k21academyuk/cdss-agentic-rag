# ============================================================================
# Clinical Decision Support System - Multi-stage Docker Build
# ============================================================================
# Stage 1: Builder - Install dependencies and build the package
# Stage 2: Runtime - Minimal image for running the FastAPI application
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies required for native extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libffi-dev \
        libssl-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only dependency specification first (Docker cache optimization)
COPY pyproject.toml README.md ./

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install the project dependencies (without the project itself)
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir .

# Copy the full source code and install the project
COPY src/ ./src/
RUN pip install --no-cache-dir . --no-deps

# ---------------------------------------------------------------------------
# Stage 2: Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install minimal runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source code
COPY src/ /app/src/
COPY sample_data/ /app/sample_data/

WORKDIR /app

# Create a non-root user for running the application
RUN groupadd --gid 1000 cdss && \
    useradd --uid 1000 --gid cdss --shell /bin/bash --create-home cdss && \
    chown -R cdss:cdss /app

USER cdss

# Expose the FastAPI application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Use tini as PID 1 for proper signal handling
ENTRYPOINT ["tini", "--"]

# Run the FastAPI application with uvicorn
CMD ["uvicorn", "cdss.api.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--access-log", \
     "--log-level", "info", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
