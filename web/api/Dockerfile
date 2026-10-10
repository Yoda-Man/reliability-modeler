# syntax=docker/dockerfile:1
#
# Reliability Modeler API image.
# Build context: repository root
#   docker build -f web/api/Dockerfile -t reliability-modeler-api .
#
# The base image is pinned by digest (python:3.13-slim multi-arch index).
# To refresh: docker buildx imagetools inspect python:3.13-slim
ARG PYTHON_IMAGE=python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

# ── Builder: compile/install dependencies into a self-contained venv ─────────
FROM ${PYTHON_IMAGE} AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# requirements.lock (fully pinned, preferred) is optional; fall back to
# requirements.txt when it is absent. The glob makes the COPY tolerate either.
COPY web/api/requirements.txt web/api/requirements.lock* ./

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && if [ -f requirements.lock ]; then REQ=requirements.lock; else REQ=requirements.txt; fi \
    && echo "Installing API dependencies from ${REQ}" \
    && /opt/venv/bin/pip install -r "${REQ}"

# ── Runtime: no compilers, non-root ──────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    CONFIG_DIR=/app/config \
    OUTPUT_DIR=/app/output \
    DEFAULT_CONFIG_PATH=/app/defaults/fault_categories.conf \
    MPLCONFIGDIR=/tmp/matplotlib

RUN useradd --create-home --uid 10001 --user-group appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Engine package + all API modules + bundled default taxonomy
COPY modeler/ /app/modeler/
COPY web/api/*.py /app/
COPY fault_categories.conf /app/defaults/fault_categories.conf

# Writable state lives only in the two volume mount points
RUN mkdir -p /app/config /app/output \
    && chown -R appuser:appuser /app/config /app/output

USER appuser

EXPOSE 8000

VOLUME ["/app/config", "/app/output"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
