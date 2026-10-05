# Multi-stage build following uv's Docker guide: the final image gets only the
# virtual environment, not uv, the build cache, or the source tree.

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /bin/

# Bytecode is compiled once at build time instead of on every container start;
# copy mode avoids hardlink warnings across the cache mount; the base image's
# Python is used so the venv works in the final stage built on the same image.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first, in their own layer: code changes don't reinstall them.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project --no-editable

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# Non-editable: the package is installed into the venv, so src isn't needed later.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


FROM python:3.13-slim

RUN useradd --create-home --uid 1000 app \
    && mkdir /data \
    && chown app:app /data

COPY --from=builder --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    CACHE_DATABASE_URL="sqlite+aiosqlite:////data/cache.db"

USER app
VOLUME ["/data"]
EXPOSE 8000

# The slim image has no curl; the venv's Python can make the request itself.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "--factory", "transform_cache.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
