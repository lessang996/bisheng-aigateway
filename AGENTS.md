# Bisheng Gateway Agent Guide

## Project layout
- `backend/` contains the FastAPI application, SQLModel models, Alembic migrations, and tests.
- `frontend/` contains the React/Vite client and is deployed independently as static assets.
- `k8s/gateway.yaml` is the production Kubernetes baseline for the API gateway.

## Runtime
- Backend entrypoint: `backend/main.py` (`uvicorn main:app`).
- Configuration is loaded from environment variables by `backend/app/core/config.py`.
- Production requires MySQL `DATABASE_URL`, Redis `REDIS_URL`, a strong `JWT_SECRET_KEY`, and upstream API credentials.
- Use `DB_AUTO_CREATE=false` in production and run Alembic migrations as a release step.
- Liveness endpoint: `/health/live`; readiness endpoint: `/health/ready`.

## Deployment conventions
- Build the root `Dockerfile`; it packages only the backend runtime and runs as non-root UID 10001.
- Inject secrets at deploy time. Never commit real credentials or `.env` files.
- Keep SSE responses transparent and preserve the existing API contract.
