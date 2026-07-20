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

All date-range tools accept `start_date` / `end_date` (ISO `YYYY-MM-DD`) and
**default to the last 7 days** when omitted.

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

## Getting an access token

The server authenticates with a single **bearer token** in `OURA_ACCESS_TOKEN`.
There are two ways to get one:

1. **Legacy Personal Access Token (PAT)** — the easy path, *if you already have
   one*. Oura **deprecated new PATs in December 2025**, so you can no longer
   create one, but tokens minted before then still work. Manage existing tokens
   at <https://cloud.ouraring.com/personal-access-tokens>.

2. **OAuth2** (required for new integrations) — register an application at
   <https://cloud.ouraring.com/oauth/applications>, then run the authorization
   code flow to obtain an access token. Oura access tokens are long-lived; a
   refresh token is also issued. (A guided `oura-mcp-server login` command that
   automates this flow is on the roadmap below — for now, paste the access token
   you obtain into `OURA_ACCESS_TOKEN`.)

Either way, the server just sends it as `Authorization: Bearer <token>`.

> **Subscription note:** an active Oura membership is required for the API to
> return most data. Without it you'll get the three daily scores at best.

## Setup

Requires Python ≥ 3.10. Using [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/sumedhkhodke/oura-mcp-server.git
cd oura-mcp-server
uv venv && uv pip install -e .
cp .env.example .env   # then edit .env and set OURA_ACCESS_TOKEN
```

Quick check that your token works:

```bash
OURA_ACCESS_TOKEN=... uv run python -c \
  "import asyncio; from oura_mcp_server.client import OuraClient; \
   print(asyncio.run(OuraClient().get_single('personal_info')))"
```

### Claude Desktop

Add to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "oura": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/oura-mcp-server", "run", "oura-mcp-server"],
      "env": { "OURA_ACCESS_TOKEN": "your_token_here" }
    }
  }
}
```

Restart Claude Desktop and ask, e.g., *"How did I sleep this week?"* or
*"What's my readiness trend and resting heart rate over the last 14 days?"*

### Claude Code

```bash
claude mcp add oura --env OURA_ACCESS_TOKEN=your_token_here \
  -- uv --directory /absolute/path/to/oura-mcp-server run oura-mcp-server
```

## Development

```bash
uv pip install -e ".[dev]"
pytest            # HTTP layer mocked with respx; no token or network needed
```

Layout:

```
src/oura_mcp_server/
  client.py   # async httpx client: bearer auth + transparent pagination
  server.py   # FastMCP app; one tool per Oura endpoint
  __main__.py # `oura-mcp-server` entry point (stdio transport)
tests/
  test_client.py
```

## Roadmap

- [ ] `login` command automating the OAuth2 authorization-code flow + token refresh
- [ ] Optional summarized/human-readable output mode (trends, deltas vs. baseline)
- [ ] Derived analytics tools (e.g. correlate sleep vs. next-day readiness)
- [ ] Webhook subscription tools for push updates
- [ ] Remote/HTTP transport option for hosted deployment
- [ ] Publish to PyPI for `uvx oura-mcp-server`

## Disclaimer

Unofficial. Not affiliated with, endorsed by, or supported by Ōura Health Oy.
Provided as-is; verify anything health-related with the Oura app and a
professional.

## License

Apache-2.0 — see [LICENSE](LICENSE).
