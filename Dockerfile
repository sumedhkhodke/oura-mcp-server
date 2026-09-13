# Lightweight image for running the Oura MCP server over HTTP (e.g. on Railway).
FROM python:3.12.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Railway mounts persistent volumes as root. The entrypoint prepares the OAuth
# state directory, then gosu drops privileges before the server starts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

# Dependencies first (cached unless the lockfile changes), then the package itself.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable \
    && chown -R appuser:appuser /app

COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Railway injects $PORT; bind all interfaces inside the container.
# HTTP transport is fail-closed: configure GitHub OAuth (see README).
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["sh", "-c", "exec oura-mcp-server serve --transport http --host 0.0.0.0 --port ${PORT:-8000}"]
