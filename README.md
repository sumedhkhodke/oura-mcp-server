<div align="center">

# oura-mcp-server

[![CI](https://github.com/sumedhkhodke/oura-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/sumedhkhodke/oura-mcp-server/actions/workflows/ci.yml) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sumedhkhodke/oura-mcp-server) [![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/) [![MCP](https://img.shields.io/badge/MCP-Model_Context_Protocol-000000?style=flat&logo=modelcontextprotocol&logoColor=white)](https://modelcontextprotocol.io) [![FastMCP](https://img.shields.io/badge/FastMCP-4.x-6E56CF?style=flat)](https://gofastmcp.com) [![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv) [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) [![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue?style=flat&logo=opensourceinitiative&logoColor=white)](LICENSE) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat)](#contributing) [![GitHub last commit](https://img.shields.io/github/last-commit/sumedhkhodke/oura-mcp-server?style=flat)](https://github.com/sumedhkhodke/oura-mcp-server/commits/main) [![GitHub issues](https://img.shields.io/github/issues/sumedhkhodke/oura-mcp-server?style=flat)](https://github.com/sumedhkhodke/oura-mcp-server/issues) [![Star History](https://img.shields.io/github/stars/sumedhkhodke/oura-mcp-server?label=Stars&logo=github&style=flat)](https://github.com/sumedhkhodke/oura-mcp-server/stargazers)

**Your Oura Ring data as read-only MCP tools for Claude: sleep, readiness, HRV, workouts, trends, and correlations.**

</div>

An [MCP](https://modelcontextprotocol.io) server for the **Oura Ring v2 API**, built with
[FastMCP](https://gofastmcp.com). It runs locally over stdio for Claude Code and Claude Desktop,
or hosted over Streamable HTTP behind GitHub OAuth for Claude web. Every tool reads your own Oura
account; the analytics tools add per-day briefings, trends, and correlations on top of the raw
endpoints.

## Quickstart

Requires Python ≥ 3.10, [uv](https://docs.astral.sh/uv/), an Oura OAuth app (see
[Authentication](#authentication)), and an active Oura membership.

```bash
git clone https://github.com/sumedhkhodke/oura-mcp-server.git
cd oura-mcp-server
uv sync
uv run oura-mcp-server login --client-id <ID> --client-secret <SECRET>   # one-time, opens your browser
claude mcp add oura -- uv --directory "$PWD" run oura-mcp-server
```

**Claude Desktop** (`claude_desktop_config.json`, macOS: `~/Library/Application Support/Claude/`):

```json
{
  "mcpServers": {
    "oura": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/oura-mcp-server", "run", "oura-mcp-server"]
    }
  }
}
```

## Tools

Date-range tools accept `start_date` / `end_date` (ISO `YYYY-MM-DD`) and default to the last
7 days when omitted.

| Tool | What you get |
| --- | --- |
| `get_daily_sleep` / `get_daily_readiness` / `get_daily_activity` | Daily scores + contributors |
| `get_sleep_periods` | Per-night stages, HR/HRV series, hypnogram |
| `get_daily_spo2` / `get_daily_stress` / `get_daily_resilience` | Blood oxygen, stress vs. recovery time, resilience |
| `get_daily_cardiovascular_age` / `get_vo2_max` | Vascular age, cardio fitness |
| `get_heart_rate` | Raw HR samples (defaults to last 24h) |
| `get_workouts` / `get_sessions` / `get_tags` | Workouts, meditation/breathing sessions, user tags |
| `get_sleep_time` / `get_rest_mode_periods` | Optimal bedtime windows, Rest Mode periods |
| `get_personal_info` / `get_ring_configuration` | Profile, ring hardware/firmware |
| `get_daily_briefing` / `get_metric_trend` / `get_metric_correlation` | Combined per-day summary, stats + direction over N days, Pearson between two metrics (optional day-lag) |
| `list/create/renew/delete_webhook_subscription` | Manage Oura push subscriptions (uses your OAuth app credentials) |
| `get_recent_webhook_events` | Events received by the built-in `/webhook` route, newest first |

Metrics for `get_metric_trend` / `get_metric_correlation`: `sleep_score`, `readiness_score`,
`activity_score`, `total_sleep_hours`, `sleep_efficiency`, `resting_heart_rate`, `average_hrv`,
`temperature_deviation`, `steps`, `active_calories`.

**Prompts:** `analyze_recovery`, `weekly_review`, `sleep_optimization`.

## Authentication

OAuth2:

1. Create an application at <https://developer.ouraring.com/> with redirect URI exactly
   `http://localhost:8080/callback` (change the port with `--port` / `OURA_REDIRECT_PORT`). The
   legacy `cloud.ouraring.com` portal can only edit apps created before the move.
2. Log in. This opens your browser, saves tokens to `~/.oura-mcp/tokens.json`, and the server
   auto-refreshes them at runtime. Re-running `login` reuses saved credentials.

   ```bash
   uv run oura-mcp-server login --client-id <ID> --client-secret <SECRET>
   ```

Credential precedence at runtime (see `auth.default_token_source`):

1. `OURA_REFRESH_TOKEN` + `OURA_CLIENT_ID` + `OURA_CLIENT_SECRET`: headless refresh mode for
   containers; the rotated pair is persisted to `OURA_TOKEN_FILE`, which then wins on restart.
2. `OURA_ACCESS_TOKEN` alone: a static bearer. A legacy (pre-Dec-2025) PAT works here; an OAuth
   access token expires after 30 days and cannot self-refresh.
3. The token file written by `login`.

See [`.env.example`](.env.example) for every variable.

## Remote / HTTP transport

For a hosted deployment, run the Streamable HTTP transport. The endpoint is `http://<host>:<port>/mcp`:

```bash
oura-mcp-server serve --transport http --host 0.0.0.0 --port 8000
```

**Auth is fail-closed:** remote clients sign in with GitHub OAuth, and only GitHub users in
`OURA_MCP_ALLOWED_GITHUB_USERS` can reach the Oura account behind this server. Shared bearer
tokens are not supported, and the server refuses to start without the variables below.

Create a GitHub OAuth App under **Settings → Developer settings → OAuth Apps**:

- Homepage URL: your public server origin, e.g. `https://<your-app>.up.railway.app`
- Authorization callback URL: that origin plus `/auth/callback`

Then configure:

```bash
OURA_MCP_GITHUB_CLIENT_ID=...
OURA_MCP_GITHUB_CLIENT_SECRET=...
OURA_MCP_ALLOWED_GITHUB_USERS=<your-github-login>  # comma-separated, case-insensitive
OURA_MCP_JWT_SIGNING_KEY=<stable random secret>    # python -c "import secrets; print(secrets.token_urlsafe(48))"
OURA_MCP_BASE_URL=https://<your-public-origin>     # not needed on Railway (derived from RAILWAY_PUBLIC_DOMAIN)
FASTMCP_HOME=/data/fastmcp                         # persistent storage for FastMCP's encrypted OAuth state
```

`OURA_MCP_JWT_SIGNING_KEY` must stay stable across deploys, and `FASTMCP_HOME` must live on
persistent storage or clients have to re-authorize after every restart.

### Reference deployment: Railway

The repo ships a `Dockerfile` and `railway.json`, so Railway builds and runs the HTTP server
directly. `login` is interactive, so the container authenticates from env instead:

```bash
railway login
railway init
railway volume add --mount-path /data
railway variables --set "OURA_CLIENT_ID=..." --set "OURA_CLIENT_SECRET=..." \
                  --set "OURA_REFRESH_TOKEN=..." \   # refresh_token from ~/.oura-mcp/tokens.json after a local login
                  --set "OURA_TOKEN_FILE=/data/oura/tokens.json" \
                  --set "FASTMCP_HOME=/data/fastmcp"
# ...plus the OURA_MCP_* variables from the section above.
railway up
railway domain
```

Oura refresh tokens are single-use and rotate on every refresh, so `OURA_TOKEN_FILE` must point
inside the volume. Otherwise a restart falls back to the already-consumed env seed and the
server can no longer refresh. `docker-entrypoint.sh` creates and chowns that directory before
dropping privileges. Railway injects `PORT`; your MCP endpoint is `https://<your-app>.up.railway.app/mcp`.
With the GitHub source connected, every push to `main` deploys.

### Connect from Claude web / Claude Code

A hosted server only admits the GitHub users on its allowlist, so you must deploy your own
rather than pointing at someone else's URL.

**Claude web:** in **Customize → Connectors**, choose **Add custom connector** and enter
`https://<your-app>.up.railway.app/mcp`. Leave the advanced client ID/secret fields empty.
Claude uses Dynamic Client Registration and opens the GitHub authorization flow when you connect.

**Claude Code:**

```bash
claude mcp add -s user --transport http oura https://<your-app>.up.railway.app/mcp
```

Run `/mcp` and authenticate in the browser when prompted.

## Claude Code plugin

The repo doubles as a Claude Code plugin bundling the MCP server (stdio, launched with `uv`) and
an `/oura` skill (conversational briefings, trends, correlations):

```bash
claude plugin marketplace add sumedhkhodke/oura-mcp-server
claude plugin install oura@oura-plugins
```

Then log in once from the installed plugin root. Marketplace installs live under
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`; `claude plugin list` shows the
installed version:

```bash
cd ~/.claude/plugins/cache/oura-plugins/oura/<version>
uv run oura-mcp-server login --client-id <ID> --client-secret <SECRET>
```

Tokens are written to `~/.oura-mcp/tokens.json`, outside the plugin directory, so they survive
plugin updates. Inside Claude Code the skill is `/oura:oura` and the tools are namespaced
`mcp__plugin_oura_oura__*`.

Deployed your own hosted server? Point the plugin at it instead by replacing `mcpServers.oura`
in `.claude-plugin/plugin.json` (or in a fork of the marketplace):

```json
{
  "mcpServers": {
    "oura": { "type": "http", "url": "https://<your-app>.up.railway.app/mcp" }
  }
}
```

Using a directly registered server instead of the plugin? Just copy the skill:
`cp -r skills/oura ~/.claude/skills/`.

## Webhooks

The HTTP server exposes a built-in `/webhook` route so Oura can push change notifications to it.
It sits outside the MCP auth layer and is gated by `OURA_WEBHOOK_VERIFICATION_TOKEN`: until that
variable is set the route answers `503`. With it set, the route answers Oura's verification
`challenge` (GET) and buffers the last 200 events in memory (POST); read them back with
`get_recent_webhook_events`. The buffer clears on restart, and events carry identifiers only.
Fetch the data with the matching `get_*` tool.

Create a subscription with `create_webhook_subscription`, passing `https://<host>/webhook` as
`callback_url` and the same token as `verification_token`. Subscriptions expire and must be
renewed with `renew_webhook_subscription`.

## Development

```bash
uv sync                                                    # installs the package + dev group
uv run ruff check . && uv run ruff format --check .        # lint + format (CI gates on both)
uv run pytest -q                                           # HTTP mocked with respx; no token needed
uvx pre-commit install                                     # optional: run the same checks on commit
```

CI runs lint plus tests on Python 3.10, 3.11, 3.12, and 3.13. Set `OURA_MCP_LOG_LEVEL=DEBUG` for
verbose server logs. The `SessionStart` hook in `.claude/settings.json` installs dependencies
only when `CLAUDE_CODE_REMOTE=true` (Claude Code on the web); it is a no-op locally.

## Contributing

Contributions are welcome. For anything larger than a small fix, please open an issue first to
discuss the change, then submit a pull request. CI (lint, format, tests on all supported Python
versions) must be green. See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## License

Apache-2.0, see [LICENSE](LICENSE). Unofficial; not affiliated with Ōura Health Oy.
Verify anything health-related with the Oura app and a professional.
