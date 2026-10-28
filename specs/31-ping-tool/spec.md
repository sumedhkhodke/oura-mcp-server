# 31-ping-tool: Add a ping MCP tool to the Oura server

**Status:** draft, awaiting human review
**Source:** #31
**Codebase access:** yes

## Summary

Add a lightweight, no-credentials-required MCP tool named `ping` to the Oura server that returns server identity and version information. The tool serves as a connectivity test and requires no Oura API calls. This is a throwaway feature to test the Factorial end-to-end workflow.

## Riskiest assumptions

- **A2:** The `server` field value is the FastMCP instance name `"oura-mcp-server"`. `[SOURCE: repo, src/oura_mcp_server/server.py:30]`: the `FastMCP(name="oura-mcp-server", ...)` instance is the module-level singleton that all tools attach to. *If wrong:* a different name is required; needs one-line change to the tool implementation.

- **A5:** The tool is implemented as an async function decorated with `@mcp.tool`, matching the pattern of every other MCP tool in the server. `[SOURCE: repo, src/oura_mcp_server/server.py]`: all 20+ existing tools are async. *If wrong:* MCP protocol may reject a sync tool; rebuild as async.

- **A7:** The ping tool is listed in a separate row or early in the README tools table as a "system/connectivity" tool, distinct from Oura data-collection tools. `[SOURCE: inferred]`: the tool serves a different purpose (server health, not data) and groups better apart from daily metrics. *If wrong:* placement is cosmetic; can move anytime.

## User scenarios

1. **User tests server connectivity.** Given the server is running, when the user calls `ping`, then they receive confirmation that the server is reachable with its name, version, and current UTC time.

2. **Tooling discovers available tools.** Given the MCP protocol enumerates tools on a server, when tooling lists available tools, then `ping` appears in the list alongside other Oura tools.

## Functional requirements

- **FR1.** The system MUST implement a no-argument MCP tool named `ping` that returns server metadata (name, version, and current UTC timestamp) without calling the Oura API.
- **FR2.** The system MUST expose the `ping` tool to MCP clients in the server's tool list, discoverable alongside other tools.
- **FR3.** The tool's response MUST be a JSON object with three fields: `server` (string, server name), `version` (string, package version), and `time_utc` (string, ISO 8601 timestamp in UTC).

## Acceptance criteria

| # | Criterion | Verifies | Mechanically checkable |
|---|---|---|---|
| AC1 | Calling `ping` returns HTTP 200 and a valid JSON object | FR1, FR3 | Yes |
| AC2 | Response JSON contains exactly the three fields: `server`, `version`, `time_utc` | FR3 | Yes |
| AC3 | `server` field equals the MCP server name | FR1 | Yes |
| AC4 | `version` field equals the package version from `__init__.py` | FR1 | Yes |
| AC5 | `time_utc` field is a valid ISO 8601 UTC timestamp (ending in Z or +00:00) | FR1, FR3 | Yes |
| AC6 | The tool takes no required arguments and no optional arguments | FR1 | Yes |
| AC7 | The tool appears in the server's tool list when MCP clients enumerate available tools | FR2 | Yes |
| AC8 | At least one unit test covers the response shape and all three fields | FR1, FR3 | Yes |
| AC9 | README lists the new tool in its tools table or summary | FR2 | Yes |

## Out of scope

- Modifying authentication systems or credentials handling
- Calling any Oura API endpoints
- Persisting state or caching responses
- Webhook integration or subscription management
- Performance or load testing
- Integration with Claude Code plugin (may be added later, not part of this spec)

## Constraints

- The tool must not require Oura credentials (stated in ticket)
- The tool must return the current server version and current UTC time (stated in ticket)
- Server name is the FastMCP instance name defined in server.py: `"oura-mcp-server"` (source: repo inspection)
- Package version is defined in `src/oura_mcp_server/__init__.py` as `__version__` (source: repo inspection)

## Key entities

**Ping Tool:** A stateless, read-only MCP tool that provides server identity and availability information. It requires no arguments and makes no API calls.

## Assumptions

- **A1.** The tool should be async (coroutine), decorated with `@mcp.tool`. `[SOURCE: repo, src/oura_mcp_server/server.py]`: every MCP tool in the codebase is async; this is a FastMCP pattern. *If wrong:* tool does not integrate with MCP protocol; rebuild with async/await.

- **A2.** The `server` field value is the FastMCP instance name `"oura-mcp-server"`. `[SOURCE: repo, src/oura_mcp_server/server.py:30]`: the module-level `mcp = FastMCP(name="oura-mcp-server", ...)` instance defines the server identity. *If wrong:* a different name constant is needed; one-line change.

- **A3.** The `version` field is sourced from `oura_mcp_server.__version__` at runtime. `[SOURCE: repo, src/oura_mcp_server/__init__.py:3]`: the string `__version__ = "0.1.1"` is the source of truth. *If wrong:* version attribute path is different; inspect __init__.py for the correct attribute.

- **A4.** The `time_utc` field is generated at tool invocation time by calling `datetime.now(timezone.utc)` and formatting as ISO 8601 (e.g., `2026-10-28T15:30:45.123456Z` or similar). `[SOURCE: explicit in requirement]`: "time_utc" implies current server time, not a static value. *If wrong:* time generation or formatting is different; affects the accuracy of connectivity testing.

- **A5.** The tool takes zero arguments (no optional, no required parameters). `[SOURCE: explicit in requirement]`: "Takes no arguments" is unambiguous. *If wrong:* tool signature is different; rebuild with different decorator parameters.

- **A6.** The ping tool does not call `_get_client()` or interact with the Oura API, because it needs no credentials (per requirement). `[SOURCE: explicit in requirement]`: "Does not call the Oura API and needs no credentials." *If wrong:* implementation would initialize OAuth unnecessarily; adds latency and potential failure modes for a tool meant to test connectivity.

- **A7.** The ping tool is listed in the README tools table in a dedicated system/connectivity row or at the top, separate from data-collection tools. `[SOURCE: inferred]`: ping serves a different purpose (server health check) from daily sleep/readiness/activity metrics. *If wrong:* listing is cosmetic; can be repositioned.

- **A8.** The test file is `tests/test_server_tools.py`, following the location of other server tool tests. `[SOURCE: repo, tests/]`: the file exists and contains async tests for tools like `get_daily_briefing`. *If wrong:* test file path is different; move test to correct location.

- **A9.** The test uses `@respx.mock` and `pytest` with async support (pytest-asyncio), matching existing tool tests. `[SOURCE: repo, tests/test_server_tools.py]`: all tool tests use this pattern. *If wrong:* testing framework or async runner is different; inspect test_server_tools.py for the right approach.

- **A10.** The ping tool response is not wrapped in an error dict (e.g., no `{"error": "..."}` on success). `[SOURCE: repo and inferred]`: tools that never error simply return their data; error dicts are reserved for tools that call the Oura API and may fail. *If wrong:* response structure would need defensive error handling; unlikely given the tool's simplicity.

## Open questions

- **Q1.** Should the timestamp precision be to microseconds (as Python's `datetime.now()` returns), or rounded to milliseconds or seconds for simplicity?
  **Proceeding as:** Full microsecond precision from `datetime.now(timezone.utc).isoformat()` (see A4). Revisit if clients need coarser precision.

- **Q2.** Should the README entry for ping be a single row in the existing tools table, or a note in a separate "System" section above the tools table?
  **Proceeding as:** Single row in the tools table (see A7). Revisit if the table structure changes.
