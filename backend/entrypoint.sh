#!/usr/bin/env bash
# Run alembic migrations on container start, then exec the uvicorn server.
#
# Why on container start: `az containerapp exec` is interactive-only (calls
# tty.setcbreak() on stdin), so it can't run migrations from CI. Putting the
# migration step here means every revision roll re-runs `alembic upgrade head`,
# which is a no-op when the DB is already at head.
#
# Concurrency: alembic acquires a Postgres advisory lock during upgrade, so
# multiple replicas starting at once converge cleanly.
set -euo pipefail

if [ "${RUN_MIGRATIONS_ON_START:-true}" = "true" ]; then
  echo "[entrypoint] Running alembic upgrade head..."
  alembic upgrade head
else
  echo "[entrypoint] RUN_MIGRATIONS_ON_START=false; skipping migrations."
fi

echo "[entrypoint] Starting uvicorn..."
exec uvicorn automunki.main:app --host 0.0.0.0 --port 8000 "$@"
