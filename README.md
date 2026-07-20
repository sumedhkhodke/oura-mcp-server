# oura-mcp-server

An [MCP](https://modelcontextprotocol.io) server that wraps the **Oura Ring v2 API**,
built with [FastMCP](https://gofastmcp.com). It exposes your sleep, readiness,
activity, HRV, heart rate, SpO2, stress, resilience, workouts, and more as MCP
tools so Claude (or any MCP client) can read and reason over your Oura data.

> **Why this exists:** Oura has no mature, official, hosted MCP server yet (their
> API legal agreement references an "MCP Server," but there's nothing you can
> point a client at). The existing community servers are mostly Node. This is a
> clean Python/FastMCP wrapper we control and extend as needed. Read-only.

## Tools

**Raw endpoint tools** — all date-range tools accept `start_date` / `end_date`
(ISO `YYYY-MM-DD`) and **default to the last 7 days** when omitted.

| Tool | Oura endpoint | What you get |
| --- | --- | --- |
| `get_daily_sleep` | `daily_sleep` | Nightly Sleep score + contributors |
| `get_daily_readiness` | `daily_readiness` | Readiness score + contributors |
| `get_daily_activity` | `daily_activity` | Steps, calories, MET minutes, Activity score |
| `get_sleep_periods` | `sleep` | Detailed per-night stages, HR/HRV series, hypnogram |
| `get_daily_spo2` | `daily_spo2` | Nightly blood-oxygen % + breathing disturbance |
| `get_daily_stress` | `daily_stress` | Daytime high-stress vs. recovery time |
| `get_daily_resilience` | `daily_resilience` | Long-term resilience level + contributors |
| `get_daily_cardiovascular_age` | `daily_cardiovascular_age` | Vascular age estimate |
| `get_vo2_max` | `vO2_max` | VO2 max (cardio fitness) estimates |
| `get_heart_rate` | `heartrate` | Raw HR samples (ISO datetimes, defaults to last 24h) |
| `get_workouts` | `workout` | Workouts: type, intensity, calories, distance |
| `get_sessions` | `session` | Meditation / breathing / rest sessions |
| `get_sleep_time` | `sleep_time` | Recommended optimal bedtime windows |
| `get_rest_mode_periods` | `rest_mode_period` | Rest Mode (illness/recovery) periods |
| `get_tags` | `enhanced_tag` | User-logged tags/notes (caffeine, naps, symptoms…) |
| `get_personal_info` | `personal_info` | Profile: age, sex, height, weight |
| `get_ring_configuration` | `ring_configuration` | Ring model, hardware, color, size, firmware |

**Analytics tools** — derived insights that stitch several endpoints together.

| Tool | What you get |
| --- | --- |
| `get_daily_briefing` | One combined per-day summary: Sleep/Readiness/Activity scores + total sleep hours, resting HR, average HRV, temperature deviation, steps, active calories. The "how am I doing?" tool. |
| `get_metric_trend` | Mean/min/max, first-vs-last change, delta-from-mean, and direction for one metric over the last N days. |
| `get_metric_correlation` | Pearson correlation between two metrics, with optional day-lag — e.g. "how does last night's sleep affect tomorrow's readiness?" |

Metrics available to the analytics tools: `sleep_score`, `readiness_score`,
`activity_score`, `total_sleep_hours`, `sleep_efficiency`, `resting_heart_rate`,
`average_hrv`, `temperature_deviation`, `steps`, `active_calories`.

**Prompts** — ready-made analyses you can pick from the MCP client's prompt menu:
`analyze_recovery`, `weekly_review`, `sleep_optimization`.

## Authentication

The server sends a bearer token as `Authorization: Bearer <token>`. Two ways to
get one, resolved automatically at runtime (env var first, then the OAuth file):

### OAuth2 (recommended — required for new integrations)

Oura **deprecated new Personal Access Tokens in December 2025**, so OAuth2 is the
path for anyone setting up fresh.

1. Go to <https://cloud.ouraring.com/oauth/applications> and **create an
   application**. Set the **redirect URI** to exactly:
   ```
   http://localhost:8080/callback
   ```
   (use a different port with `--port` / `OURA_REDIRECT_PORT`; the registered
   URI must match). Note the **client ID** and **client secret**.
2. Run the login command — it opens your browser, you approve, and tokens are
   saved to `~/.oura-mcp/tokens.json` (chmod 600):
   ```bash
   oura-mcp-server login --client-id <ID> --client-secret <SECRET>
   # or set OURA_CLIENT_ID / OURA_CLIENT_SECRET and just: oura-mcp-server login
   ```
3. Start the server normally. It reads the token file and **auto-refreshes** the
   access token (using the stored refresh token) whenever it expires — no env
   vars needed at runtime.

### Legacy Personal Access Token (only if you already have one)

Existing pre-Dec-2025 PATs still work. Set `OURA_ACCESS_TOKEN=<token>` and skip
the login step. Manage existing tokens at
<https://cloud.ouraring.com/personal-access-tokens>. (This path can't
self-refresh, but PATs are long-lived.)

> **Subscription note:** an active Oura membership is required for the API to
> return most data. Without it you'll get the three daily scores at best.

## Setup

Requires Python ≥ 3.10. Using [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/sumedhkhodke/oura-mcp-server.git
cd oura-mcp-server
uv venv && uv pip install -e .
cp .env.example .env   # fill in OAuth creds (or a legacy OURA_ACCESS_TOKEN)
```

Authenticate (OAuth2 — see [Authentication](#authentication) for app setup):

```bash
uv run oura-mcp-server login --client-id <ID> --client-secret <SECRET>
```

Quick check it works (reads the saved OAuth token, or `OURA_ACCESS_TOKEN`):

```bash
uv run python -c \
  "import asyncio; from oura_mcp_server.client import OuraClient; \
   print(asyncio.run(OuraClient().get_single('personal_info')))"
```

### Claude Desktop

Add to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`).
After `oura-mcp-server login`, no token env var is needed — the server reads
`~/.oura-mcp/tokens.json` and auto-refreshes:

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

Using a legacy PAT instead? Add `"env": { "OURA_ACCESS_TOKEN": "your_token" }`.
Restart Claude Desktop and ask, e.g., *"How did I sleep this week?"* or
*"What's my readiness trend and resting heart rate over the last 14 days?"*

### Claude Code

```bash
# after `oura-mcp-server login`:
claude mcp add oura -- uv --directory /absolute/path/to/oura-mcp-server run oura-mcp-server
```

## Development

```bash
uv pip install -e ".[dev]"
pytest            # HTTP layer mocked with respx; no token or network needed
```

Layout:

```
src/oura_mcp_server/
  auth.py      # token sources: static (env) + auto-refreshing OAuth store
  oauth.py     # `login` loopback authorization-code flow
  client.py    # async httpx client: bearer auth, pagination, 401-refresh retry
  analytics.py # per-day records, trend stats, Pearson correlation
  server.py    # FastMCP app: raw + analytics tools, prompt templates
  __main__.py  # `oura-mcp-server` entry point (serve / login)
tests/         # respx-mocked; no token or network needed
```

## Roadmap

- [x] `login` command automating the OAuth2 authorization-code flow + token refresh
- [x] Derived analytics tools (daily briefing, trends, correlations)
- [x] Analysis prompt templates
- [ ] Webhook subscription tools for push updates
- [ ] Remote/HTTP transport option for hosted deployment
- [ ] Publish to PyPI for `uvx oura-mcp-server`

## Disclaimer

Unofficial. Not affiliated with, endorsed by, or supported by Ōura Health Oy.
Provided as-is; verify anything health-related with the Oura app and a
professional.

## License

Apache-2.0 — see [LICENSE](LICENSE).
