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

# Install the package + dev dependency group (pytest, ruff, ...) into .venv from
# the lockfile. Idempotent; re-runnable. Use `uv run <cmd>` to invoke tools.
uv sync --locked

# Surface the ruff lint + format status at startup. Non-fatal: a finding must
# not block the session from starting (set -e would otherwise abort here).
echo "session-start: running ruff lint + format check (informational)..."
uv run ruff check . || echo "session-start: ruff lint reported issues (see above); not blocking startup."
uv run ruff format --check . || echo "session-start: ruff format would reformat files; run 'uv run ruff format .' (not blocking)."

echo "session-start: oura-mcp-server dev environment ready."
