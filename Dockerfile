# Lightweight image for running the Oura MCP server over HTTP (e.g. on Railway).
FROM python:3.12-slim

# Faster, quieter Python; no .pyc, unbuffered logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first (better layer caching), then the package.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

# Run as non-root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# Railway injects $PORT; bind all interfaces inside the container.
# HTTP transport is fail-closed: set OURA_MCP_AUTH_TOKEN (see README).
ENV HOST=0.0.0.0
EXPOSE 8000
CMD ["sh", "-c", "oura-mcp-server serve --transport http --host 0.0.0.0 --port ${PORT:-8000}"]
