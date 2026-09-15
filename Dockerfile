FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv

COPY backend/pyproject.toml backend/uv.lock /app/backend/

RUN uv sync \
    --directory /app/backend \
    --locked \
    --no-dev \
    --no-install-project

RUN test -x /app/backend/.venv/bin/python \
    && test -x /app/backend/.venv/bin/uvicorn \
    && /app/backend/.venv/bin/python -c "import uvicorn; print('builder uvicorn:', uvicorn.__version__)"


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONPATH=/app/backend \
    PATH=/app/backend/.venv/bin:$PATH

WORKDIR /app

RUN addgroup --system --gid 10001 appgroup \
    && adduser --system --uid 10001 --ingroup appgroup appuser \
    && mkdir -p /app/backend/logs \
    && chown -R 10001:10001 /app

COPY --from=builder --chown=10001:10001 \
    /app/backend/.venv \
    /app/backend/.venv

COPY --chown=10001:10001 \
    backend/main.py \
    backend/alembic.ini \
    /app/backend/

COPY --chown=10001:10001 \
    backend/app \
    /app/backend/app

COPY --chown=10001:10001 \
    backend/alembic \
    /app/backend/alembic

RUN /app/backend/.venv/bin/python --version \
    && /app/backend/.venv/bin/python -c "import uvicorn; print('runtime uvicorn:', uvicorn.__version__)" \
    && /app/backend/.venv/bin/uvicorn --version

WORKDIR /app/backend

USER 10001:10001

EXPOSE 8080

CMD ["sh", "-c", "exec /app/backend/.venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers ${WEB_CONCURRENCY:-2}"]