#!/bin/sh
set -eu

# Railway mounts volumes as root. Prepare only the configured FastMCP state
# directory, then drop privileges before starting the server.
fastmcp_home="${FASTMCP_HOME:-/data/fastmcp}"
mkdir -p "$fastmcp_home"
chown -R appuser:appuser "$fastmcp_home"

if [ -n "${OURA_TOKEN_FILE:-}" ]; then
    token_dir="$(dirname "$OURA_TOKEN_FILE")"
    mkdir -p "$token_dir"
    chown appuser:appuser "$token_dir"
    [ -f "$OURA_TOKEN_FILE" ] && chown appuser:appuser "$OURA_TOKEN_FILE"
fi

exec gosu appuser "$@"
