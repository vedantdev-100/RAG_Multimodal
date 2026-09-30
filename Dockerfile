FROM python:3.12-slim

# Pin uv itself to an exact version too — an "uv upgraded itself and
# resolved differently" incident is exactly what uv.lock + --locked
# already prevents at the dependency level; pinning the installer closes
# the same gap one level up.
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /usr/local/bin/

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    # Docling's dependency chain (opencv, via docling-ibm-models) needs
    # these even in "headless" mode on a slim base image.
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifests first for Docker layer caching.
COPY pyproject.toml uv.lock .python-version ./

# --locked: build fails loudly if the lock file doesn't match pyproject.toml,
# rather than silently re-resolving inside the image.
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv sync --locked --no-dev

EXPOSE 8000
# MODELS_DIR must be populated before this serves real traffic:
#   docker compose run --rm app uv run python -m app.cli.download_models
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
