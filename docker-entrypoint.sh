#!/bin/sh
set -eu

# Railway mounts volumes as root. Prepare only the configured FastMCP state
# directory, then drop privileges before starting the server.
fastmcp_home="${FASTMCP_HOME:-/data/fastmcp}"
mkdir -p "$fastmcp_home"
chown -R appuser:appuser "$fastmcp_home"

exec gosu appuser "$@"
