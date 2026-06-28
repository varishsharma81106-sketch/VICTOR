# Victor — Local-First Research Intelligence System
# Multi-stage build for production deployment

# ---------------------------------------------------------------------------
# Stage 1: Base
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Development
# ---------------------------------------------------------------------------
FROM base AS dev

RUN pip install --no-cache-dir pytest ruff

COPY . .
RUN pip install -e .

ENV VICTOR_HOME=/app/.victor
ENV PYTHONPATH=/app

CMD ["python", "-m", "victor.cli", "--mock-llm", "stats"]

# ---------------------------------------------------------------------------
# Stage 3: Production
# ---------------------------------------------------------------------------
FROM base AS prod

COPY . .
RUN pip install -e .

ENV VICTOR_HOME=/data/.victor
VOLUME ["/data"]

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from victor.core import Victor; v = Victor(); print('OK')" || exit 1

ENTRYPOINT ["python", "-m", "victor.cli"]
CMD ["--help"]
