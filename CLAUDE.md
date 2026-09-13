# CLAUDE.md

FastMCP server exposing one Oura Ring account's v2 API data as read-only MCP tools. Python >= 3.10, `httpx`, `uv`; runs locally over stdio or hosted on Railway over Streamable HTTP.

## Project map

- `src/oura_mcp_server/server.py` - every `@mcp.tool` / `@mcp.prompt`, the `/webhook` route, and `run()`
- `src/oura_mcp_server/client.py` - `OuraClient`: bearer injection, refresh-on-401, `next_token` pagination, error mapping
- `src/oura_mcp_server/auth.py` - Oura token sources and the env/file precedence resolver
- `src/oura_mcp_server/oauth.py` - `login` subcommand: loopback OAuth flow, default scopes
- `src/oura_mcp_server/mcp_auth.py` - GitHub OAuth proxy that gates MCP clients on the hosted server
- `src/oura_mcp_server/analytics.py` - per-day metric records, trends, Pearson correlation
- `src/oura_mcp_server/webhook.py`, `webhook_receiver.py` - Oura push subscriptions and the in-memory event buffer
- `tests/` - pytest + respx, no live Oura calls
- `skills/oura/SKILL.md`, `.claude-plugin/` - the `/oura` skill and Claude Code plugin packaging
- `Dockerfile`, `docker-entrypoint.sh`, `railway.json` - hosted deployment

<important if="you need to run commands to set up, test, lint, or run the server">

```bash
uv sync                                                                # first-time setup; dev group installs by default
uv run pytest -q                                                       # full suite, no Oura token needed
uv run pytest tests/test_client.py -k pagination                       # single file / single test
uv run pytest --cov=oura_mcp_server --cov-report=term-missing          # coverage (CI does not gate on it)
uv run ruff check . && uv run ruff format --check .                    # CI gates on both
uv run ruff format .                                                   # apply formatting
uv lock --check                                                        # CI fails if uv.lock drifts from pyproject
uvx pre-commit install                                                 # optional: ruff + uv-lock hooks on commit
uv run oura-mcp-server login --client-id <ID> --client-secret <SECRET> # one-time OAuth login, writes ~/.oura-mcp/tokens.json
uv run oura-mcp-server                                                 # stdio server (what Claude Desktop/Code launch)
uv run oura-mcp-server serve --transport http --port 8000              # hosted mode; refuses to start without GitHub OAuth env
```

CI runs lint, `uv lock --check`, and tests on Python 3.10 through 3.14, installing with `uv sync --locked`. Dev dependencies are a PEP 735 `[dependency-groups]` group, not an extra.
</important>

<important if="you are adding or modifying MCP tools or prompts">

- Tools live on the single module-level `FastMCP` instance in `server.py` and get the Oura client through `_get_client()`, a lazy process-wide singleton.
- Date-range tools delegate to `_collection()`, which fills a 7-day default window; follow that pattern rather than computing dates per tool.
- Return `{"error": ...}` dicts on `OuraError` instead of raising, so the assistant sees the message.
- Update the `allowed-tools` list in `skills/oura/SKILL.md` when adding or renaming a tool. Each tool is listed twice: `mcp__oura__*` for a directly registered server and `mcp__plugin_oura_oura__*` for the plugin install.
- Date and datetime inputs go through `_parse_date` / `_parse_datetime` (trailing `Z` accepted) and bad input returns an error dict, never raises.
</important>

<important if="you are touching authentication, tokens, OuraClient construction, or the login flow">

Two unrelated auth systems exist. `auth.py`/`oauth.py` is how this server reaches the Oura API. `mcp_auth.py` is how MCP clients prove they may use the hosted server, via GitHub OAuth plus a login allowlist, and it is fail-closed for `--transport http`.

Oura-side precedence, implemented in `auth.default_token_source()`:

1. `OURA_REFRESH_TOKEN` + `OURA_CLIENT_ID` + `OURA_CLIENT_SECRET` in env yields a refreshable source. An existing token file wins over the env seed.
2. `OURA_ACCESS_TOKEN` alone is static and never refreshes.
3. Otherwise the token file written by `login`.

`OuraClient()` with no arguments must always delegate to that resolver. A shortcut that checked `OURA_ACCESS_TOKEN` first once left the hosted server unable to refresh for a month; `tests/test_client.py` guards against it, and `tests/test_auth.py` covers the precedence rules. Add a case there when changing resolution.

Refresh is serialized with an `asyncio.Lock` because the refresh token is single-use; two concurrent callers must produce one POST. Refresh attempts, successes, and failures are logged on the `oura_mcp_server.auth` logger. Logging is configured in `__main__.py` to stderr, level from `OURA_MCP_LOG_LEVEL`.

Oura refresh tokens are single-use and rotate on every refresh. Access tokens expire after 30 days. The rotated pair is written to `OURA_TOKEN_FILE`, default `~/.oura-mcp/tokens.json`.

The Oura OAuth app is managed in Oura's new developer portal at developer.ouraring.com. The legacy portal's move re-issued client secrets.
</important>

<important if="you are working on webhooks or the /webhook route">

- Subscription management authenticates with the OAuth application credentials as `x-client-id` / `x-client-secret` headers, not the user bearer token.
- The `/webhook` route is mounted outside the MCP auth layer and gated by `OURA_WEBHOOK_VERIFICATION_TOKEN`. Events go into a 200-entry in-memory buffer that is lost on restart.
</important>

<important if="you are writing or modifying tests">

- Every Oura call is mocked with `respx`; nothing hits the network.
- Tool tests set `OURA_ACCESS_TOKEN` and reset `server._client = None` in a fixture so the singleton picks up the env, then await the tool functions directly. See the `server` fixture in `tests/test_server_tools.py`.
</important>

<important if="you are deploying, changing Railway config, the Dockerfile, the entrypoint, or environment variables">

- Pushes to `main` deploy automatically from the connected GitHub source. Merging a PR is the release.
- The `Dockerfile` CMD owns startup. Do not add `startCommand` to `railway.json`; it runs without a shell and `$PORT` will not expand.
- A volume is mounted at `/data`. `OURA_TOKEN_FILE` must point inside it, currently `/data/oura/tokens.json`, or a restart falls back to an already-consumed env refresh token. `docker-entrypoint.sh` creates and chowns that directory before dropping to `appuser`.
- Required service variables: the three Oura refresh credentials, `OURA_TOKEN_FILE`, `FASTMCP_HOME=/data/fastmcp`, the `OURA_MCP_GITHUB_*` OAuth app settings, `OURA_MCP_ALLOWED_GITHUB_USERS`, and a stable `OURA_MCP_JWT_SIGNING_KEY`. Optional: `OURA_WEBHOOK_VERIFICATION_TOKEN`, `OURA_MCP_LOG_LEVEL`.
- The image installs from `uv.lock` with `uv sync --locked --no-dev`; a dependency change needs a relock before it ships.
- If the volume is ever lost, run `login` locally and re-seed `OURA_REFRESH_TOKEN`.
</important>

<important if="you are editing the Claude Code plugin, skill, or session hook">

- `.claude-plugin/plugin.json` launches the server over stdio from `${CLAUDE_PLUGIN_ROOT}` with `uv run`, so any installer uses their own Oura account. The hosted HTTP form is documented in the README as an alternative.
- `.claude/hooks/session-start.sh` runs `uv sync --locked` and ruff only when `CLAUDE_CODE_REMOTE=true`. It is a no-op locally.
</important>
