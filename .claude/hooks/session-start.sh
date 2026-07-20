#!/bin/bash
# SessionStart hook: install dependencies so tests run in Claude Code on the web.
# Synchronous (no async line) so deps are guaranteed ready before the session starts.
set -euo pipefail

# Only run in remote (Claude Code on the web) sessions.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Ensure uv is available.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Install the package + dev deps into the system environment so `pytest` and
# `oura-mcp-server` work without activating a venv. Idempotent; re-runnable.
uv pip install --system -e ".[dev]"

echo "session-start: oura-mcp-server dev environment ready."
