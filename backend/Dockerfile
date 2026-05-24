FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the entire project before `pip install .` so hatchling can find the
# `automunki/` package directory at build time. (Splitting pyproject.toml off
# for layer caching is tempting but breaks the wheel build, which needs the
# source tree to determine which files to ship.)
COPY . .

# Install with the [azure] extra so the Azure Blob storage backend
# (azure-storage-blob, azure-identity) is available when STORAGE_BACKEND=azure_blob.
# Local dev installs (uv sync) skip this extra by default; see pyproject.toml.
RUN pip install --no-cache-dir ".[azure]"

EXPOSE 8000

# entrypoint.sh runs `alembic upgrade head` on start, then execs uvicorn.
# We can't migrate from CI (`az containerapp exec` is interactive-only and
# fails in non-TTY runners with `termios.error: Inappropriate ioctl for
# device`), so migrations are gated on container start instead. Set
# RUN_MIGRATIONS_ON_START=false to skip when needed.
CMD ["/app/entrypoint.sh"]
