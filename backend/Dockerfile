FROM python:3.15.0b3-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# Copy lockfile and project metadata first for layer caching, then the rest.
COPY pyproject.toml uv.lock ./
COPY . .

# Install with the [azure] extra so the Azure Blob storage backend
# (azure-storage-blob, azure-identity) is available when STORAGE_BACKEND=azure_blob.
# Local dev installs (uv sync) skip this extra by default; see pyproject.toml.
# --frozen ensures the lockfile is respected exactly (no version drift vs. local).
RUN uv sync --frozen --extra azure --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# entrypoint.sh runs `alembic upgrade head` on start, then execs uvicorn.
# We can't migrate from CI (`az containerapp exec` is interactive-only and
# fails in non-TTY runners with `termios.error: Inappropriate ioctl for
# device`), so migrations are gated on container start instead. Set
# RUN_MIGRATIONS_ON_START=false to skip when needed.
CMD ["/app/entrypoint.sh"]
