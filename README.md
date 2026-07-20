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

**Webhook tools** — manage Oura push subscriptions (Oura POSTs to your callback
when new data arrives, instead of polling). These use your OAuth **app**
credentials, and creating one requires a publicly reachable callback that echoes
Oura's verification challenge — see [Webhooks](#webhooks).

| Tool | What it does |
| --- | --- |
| `list_webhook_subscriptions` | List active subscriptions |
| `create_webhook_subscription` | Subscribe (`callback_url`, `verification_token`, `event_type`, `data_type`) |
| `renew_webhook_subscription` | Renew before expiry |
| `delete_webhook_subscription` | Remove a subscription |

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

### Remote / HTTP transport

For a hosted deployment (reachable over the network instead of launched per
client), run the Streamable HTTP transport:

```bash
oura-mcp-server serve --transport http --host 0.0.0.0 --port 8000
# endpoint: http://<host>:8000/mcp
```

Point an HTTP-capable MCP client at that URL. Put it behind TLS/auth for any
non-local exposure — it serves your Oura data.

## Webhooks

`create_webhook_subscription` registers a push subscription so Oura notifies a
callback URL when new data of a `data_type` (e.g. `daily_sleep`, `workout`) is
created/updated/deleted. Two things to know:

- **App credentials, not a user token.** Webhook calls use `OURA_CLIENT_ID` /
  `OURA_CLIENT_SECRET` (also saved by `oura-mcp-server login`).
- **Verification handshake.** On create, Oura sends a GET to your `callback_url`
  with a `challenge`; your endpoint must echo it back as JSON `{"challenge": ...}`.
  So stand up a publicly reachable callback first. Subscriptions expire —
  `renew_webhook_subscription` extends them.

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
  webhook.py   # webhook subscription client (app-credential auth)
  server.py    # FastMCP app: raw + analytics + webhook tools, prompts
  __main__.py  # `oura-mcp-server` entry point (serve [--transport] / login)
tests/         # respx-mocked; no token or network needed
.github/workflows/  # CI (tests on 3.10-3.12) + PyPI publish (trusted publishing)
```

CI runs the suite on every push/PR. A tagged release (`v*`) builds and publishes
to PyPI via Trusted Publishing — configure this repo as a trusted publisher at
<https://pypi.org/manage/account/publishing/> first (no API token needed).

## Roadmap

- [x] `login` command automating the OAuth2 authorization-code flow + token refresh
- [x] Derived analytics tools (daily briefing, trends, correlations)
- [x] Analysis prompt templates
- [x] Webhook subscription tools for push updates
- [x] Remote/HTTP transport option for hosted deployment
- [x] PyPI publish workflow (Trusted Publishing) — run a release to ship `uvx oura-mcp-server`

## Disclaimer

Unofficial. Not affiliated with, endorsed by, or supported by Ōura Health Oy.
Provided as-is; verify anything health-related with the Oura app and a
professional.

## License

Apache-2.0 — see [LICENSE](LICENSE).
