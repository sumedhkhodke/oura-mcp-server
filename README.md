# oura-mcp-server

An [MCP](https://modelcontextprotocol.io) server for the **Oura Ring v2 API**, built
with [FastMCP](https://gofastmcp.com). Exposes your sleep, readiness, activity, HRV,
heart rate, SpO2, stress, resilience, workouts, and more as read-only MCP tools for
Claude or any MCP client.

## Tools

Date-range tools accept `start_date` / `end_date` (ISO `YYYY-MM-DD`) and default to
the last 7 days when omitted.

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

**Analytics** — `get_daily_briefing` (combined per-day summary — the "how am I
doing?" tool), `get_metric_trend` (stats + direction over N days),
`get_metric_correlation` (Pearson between two metrics, optional day-lag). Metrics:
`sleep_score`, `readiness_score`, `activity_score`, `total_sleep_hours`,
`sleep_efficiency`, `resting_heart_rate`, `average_hrv`, `temperature_deviation`,
`steps`, `active_calories`.

**Webhooks** — `list/create/renew/delete_webhook_subscription` manage Oura push
subscriptions. These use your OAuth app credentials from the environment or saved by
`login`; creating one requires a publicly reachable callback that echoes Oura's
verification `challenge` back as JSON `{"challenge": ...}`.

**Prompts** — `analyze_recovery`, `weekly_review`, `sleep_optimization`.

## Authentication

OAuth2 (Oura deprecated new Personal Access Tokens in December 2025):

1. Create an application at <https://cloud.ouraring.com/oauth/applications> with
   redirect URI exactly `http://localhost:8080/callback` (change the port with
   `--port` / `OURA_REDIRECT_PORT`).
2. Log in — opens your browser, saves tokens to `~/.oura-mcp/tokens.json`, and the
   server auto-refreshes them at runtime. Re-running `login` reuses saved credentials.

   ```bash
   oura-mcp-server login --client-id <ID> --client-secret <SECRET>
   ```

Have a legacy (pre-Dec-2025) PAT? Set `OURA_ACCESS_TOKEN=<token>` and skip `login`.

> An active Oura membership is required for the API to return most data.

## Setup

Requires Python ≥ 3.10 and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/sumedhkhodke/oura-mcp-server.git
cd oura-mcp-server
uv venv && uv pip install -e .
uv run oura-mcp-server login --client-id <ID> --client-secret <SECRET>
```

**Claude Code:**

```bash
claude mcp add oura -- uv --directory /absolute/path/to/oura-mcp-server run oura-mcp-server
```

**Claude Desktop** (`claude_desktop_config.json`, macOS:
`~/Library/Application Support/Claude/`):

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

## Remote / HTTP transport

For a hosted deployment, run the Streamable HTTP transport — endpoint
`http://<host>:<port>/mcp`:

```bash
oura-mcp-server serve --transport http --host 0.0.0.0 --port 8000
```

**Auth is fail-closed:** remote clients sign in with GitHub OAuth, and only GitHub
users in `OURA_MCP_ALLOWED_GITHUB_USERS` can access the personal Oura account
behind this server. Shared bearer tokens are not supported.

Create a GitHub OAuth App under **Settings → Developer settings → OAuth Apps**:

- Homepage URL: your public server origin, such as
  `https://oura-mcp-server-production-fa2e.up.railway.app`
- Authorization callback URL: that origin plus `/auth/callback`

Then configure:

```bash
OURA_MCP_GITHUB_CLIENT_ID=...
OURA_MCP_GITHUB_CLIENT_SECRET=...
OURA_MCP_ALLOWED_GITHUB_USERS=sumedhkhodke
OURA_MCP_JWT_SIGNING_KEY=<stable random secret>
FASTMCP_HOME=/data/fastmcp
```

`OURA_MCP_JWT_SIGNING_KEY` must remain stable. Mount persistent storage at
`/data` so FastMCP's encrypted OAuth registrations and tokens survive restarts.
Outside Railway, also set `OURA_MCP_BASE_URL` to the server's public HTTPS origin;
Railway derives it from `RAILWAY_PUBLIC_DOMAIN`.

### Deploy to Railway

The repo ships a `Dockerfile` and `railway.json`, so Railway builds and runs the
HTTP server directly:

```bash
railway login
railway init
railway variables --set "OURA_CLIENT_ID=..." --set "OURA_CLIENT_SECRET=..." \
                  --set "OURA_REFRESH_TOKEN=..."   # refresh_token from ~/.oura-mcp/tokens.json
# Set the client-facing OAuth variables shown above and mount a volume at /data.
railway up
railway domain
```

The `login` flow is interactive, so containers authenticate via env instead: with
`OURA_REFRESH_TOKEN` + client credentials set, the server mints and refreshes its
own access tokens and persists the rotated pair to `OURA_TOKEN_FILE`. (A static
`OURA_ACCESS_TOKEN` also works, but only a legacy PAT is long-lived enough on its
own; OAuth access tokens expire after 30 days.) Railway injects `PORT`; your MCP endpoint is
`https://<app>.up.railway.app/mcp`.

### Claude web

In **Customize → Connectors**, choose **Add custom connector** and enter:

```text
https://oura-mcp-server-production-fa2e.up.railway.app/mcp
```

Leave the advanced client ID/secret fields empty. Claude uses Dynamic Client
Registration and opens the GitHub authorization flow when you connect.

### Claude Code

```bash
claude mcp add -s user --transport http oura https://<app>.up.railway.app/mcp
```

Run `/mcp` and authenticate in the browser when prompted.

## Claude Code plugin

The repo doubles as a Claude Code plugin bundling the hosted MCP server and a
`/oura` skill (conversational briefings, trends, correlations):

```bash
claude plugin marketplace add sumedhkhodke/oura-mcp-server
claude plugin install oura@oura-plugins
```

Using a directly registered server instead? Just copy the skill:
`cp -r skills/oura ~/.claude/skills/`.

## Development

```bash
uv pip install -e ".[dev]"
ruff check . && ruff format --check .   # lint + format (CI gates on both)
pytest                                  # HTTP mocked with respx; no token needed
```

## License

Apache-2.0 — see [LICENSE](LICENSE). Unofficial; not affiliated with Ōura Health Oy.
Verify anything health-related with the Oura app and a professional.
