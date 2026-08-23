# ============================================================
# Backend image — serves the Django API and runs the Celery worker.
# ============================================================
# One image, two roles. The web service and the worker run identical code and
# must have identical dependencies; building them separately is how they drift
# until a task fails on the worker for a library the API had all along.
# docker-compose.yml picks the role with the `command:` it passes.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libpq5     — psycopg's runtime library
# libgomp1   — OpenMP, required by faiss-cpu and onnxruntime
# curl       — the container healthcheck
RUN apt-get update && apt-get install --no-install-recommends -y \
        libpq5 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies are copied and installed before the source so that editing a
# .py file does not invalidate the (slow) pip layer.
COPY requirements.txt requirements-prod.txt ./

# ------------------------------------------------------------
FROM base AS development

COPY requirements-dev.txt ./
# requirements-prod rather than the full requirements.txt, plus the test tooling.
#
# The full file pulls PyTorch through sentence-transformers — around 800 MB,
# which turned the documented `docker compose up --build` quick-start into a
# very long first run for a dependency nothing in the default configuration
# uses. The ONNX embedding backend is what actually runs, and reranking (the
# only feature that needs PyTorch) is off by default.
#
# To exercise reranking or EMBEDDING_BACKEND=torch in a container:
#   docker compose build --build-arg INSTALL_TORCH=1 api
ARG INSTALL_TORCH=0
RUN pip install -r requirements-prod.txt -r requirements-dev.txt \
    && if [ "$INSTALL_TORCH" = "1" ]; then pip install sentence-transformers==3.1.1; fi

COPY . .

# Never run as root: a path-traversal or file-write bug in the upload handler is
# far less interesting to an attacker without it.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/media /app/indexes /app/logs /app/staticfiles \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ------------------------------------------------------------
FROM base AS production

RUN pip install -r requirements-prod.txt gunicorn==23.0.0

COPY . .

RUN python -c "import compileall; compileall.compile_dir('.', quiet=2)" || true

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/media /app/indexes /app/logs /app/staticfiles \
    && chown -R appuser:appuser /app
USER appuser

# collectstatic needs a settings module that imports cleanly. production.py
# refuses to boot without a real SECRET_KEY, so a throwaway one is supplied for
# this build step only — it is never the key the container runs with.
RUN DJANGO_ENV=development SECRET_KEY=build-only-not-a-runtime-key \
    python manage.py collectstatic --no-input --clear

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health/ || exit 1

# 1 worker, 4 threads: each worker process loads its own copy of the embedding
# model, so extra workers cost hundreds of MB. Threads keep the API responsive
# while one request is waiting on Groq.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "180", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
