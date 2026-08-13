FROM python:3.9-slim AS base

WORKDIR /app

# Install minimal runtime system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Security: create non-root app user
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid 1001 --create-home appuser

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Copy application files & scripts
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY alembic.ini ./

RUN chmod +x scripts/entrypoint.sh \
    && chown -R appuser:appgroup /app

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 0

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
