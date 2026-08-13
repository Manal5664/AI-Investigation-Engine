# syntax=docker/dockerfile:1
#
# Production-oriented image for EvidenceAI.
# The image installs runtime dependencies only; development/test tooling and
# the .env file never enter the build context. No API keys are baked in.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Non-root runtime user (uid 1000). Debian slim needs `passwd` for useradd.
RUN apt-get update \
    && apt-get install -y --no-install-recommends passwd \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

# Copy dependency manifests first for Docker layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application + Alembic migration files.
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENV HOST=0.0.0.0 \
    PORT=8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:{0}/health/live'.format(os.environ.get('PORT', '8000')), timeout=3)"]

# Deterministic startup command. HOST/PORT come from the environment so a
# platform-injected PORT works without rebuilding. Single worker keeps the
# process-local vector/graph stores consistent (see README limitations).
CMD ["sh", "-c", "python -m uvicorn app.main:app --host ${HOST} --port ${PORT}"]
