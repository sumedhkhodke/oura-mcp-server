# 31-ping-tool: Add a `ping` MCP tool for server diagnostics

**Status:** draft, awaiting human review
**Source:** Issue #31
**Codebase access:** yes

## Summary

Add a simple, stateless MCP tool named `ping` that returns the server name, package version, and current UTC timestamp. This tool requires no arguments and does not call the Oura API or require user credentials. It serves as a lightweight health check and connection test for MCP clients, and as a throwaway feature to test the Factorial connection end-to-end.

## Riskiest assumptions

- **A1.** The response contains exactly the three requested fields (`server`, `version`, `time_utc`), with no wrapper dict or metadata. `[SOURCE: request]` - the ticket specifies the exact JSON shape. *If wrong:* clients expecting a simple object get nested data; requires structural change to response and all tests.

- **A2.** The `time_utc` field uses Python's `datetime.isoformat()` default format (e.g., `2026-10-28T16:30:45.123456+00:00`), not a string ending in `Z`. `[SOURCE: inferred]` - the request says "ISO 8601 timestamp" but does not specify the variant; Python stdlib defaults to `+HH:MM` notation. *If wrong:* clients parsing `Z` suffix will fail; requires changing the timestamp format and updating AC5.

- **A3.** The tool will never raise an exception and has no error path. `[SOURCE: inferred]` - the tool does not call external APIs or access state that could fail, so error handling is unnecessary. *If wrong:* a test expects error-case coverage; the tool remains trivial and has only a happy path.

## User scenarios

1. **An MCP client verifies connectivity.** Given a connected MCP client, when it calls `ping`, then it receives the server name, version, and a UTC timestamp proving the server is responding.

2. **A user checks server version.** Given a user who has deployed the Oura MCP server and wants to verify which version is running, when they call `ping`, then they can read the version from the response.

3. **A system monitors server uptime.** Given an automated monitoring system connected to the MCP server, when it calls `ping` periodically, then it can verify the server is alive and responding without authentication.

## Functional requirements

- **FR1.** The system MUST expose an MCP tool named `ping` that requires no arguments.
- **FR2.** When invoked, the `ping` tool MUST return a JSON object with exactly three fields: `server`, `version`, and `time_utc`.
- **FR3.** The `server` field MUST contain the string `"oura-mcp-server"` (the name of the FastMCP instance).
- **FR4.** The `version` field MUST contain the current package version as a string (imported from `__init__.py`).
- **FR5.** The `time_utc` field MUST contain the current date and time in ISO 8601 format (UTC timezone).
- **FR6.** The tool MUST NOT call the Oura API, make HTTP requests to external services, or require user credentials.
- **FR7.** The tool MUST be registered with the FastMCP instance and appear in the server's advertised tool list.

## Acceptance criteria

| # | Criterion | Verifies |
|---|---|---|
| AC1 | The `ping` tool is defined in `src/oura_mcp_server/server.py` with the `@mcp.tool` decorator | FR1, FR7 |
| AC2 | Calling the `ping` tool returns a dict with keys `server`, `version`, and `time_utc` | FR2 |
| AC3 | The `server` field value is exactly `"oura-mcp-server"` | FR3 |
| AC4 | The `version` field value matches the string in `src/oura_mcp_server/__init__.py` under `__version__` | FR4 |
| AC5 | The `time_utc` field value is a string in ISO 8601 format (e.g., `2026-10-28T16:30:45.123456+00:00` or `2026-10-28T16:30:45Z`) | FR5 |
| AC6 | A unit test in `tests/` calls `ping()` and asserts the response contains all three fields with correct types | FR2, FR7 |
| AC7 | The test verifies the response shape but does not hardcode timestamp or version values | FR2 |
| AC8 | The README.md tools table includes a one-line entry for `ping` describing it as a health check or connection test | FR1, FR7 |
| AC9 | No HTTP requests are made to `api.ouraring.com` or any external service when `ping()` is called | FR6 |
| AC10 | [NOT MECHANICALLY CHECKABLE] The tool is clearly described as stateless and requiring no credentials in its docstring | FR6 |

## Out of scope

- Authentication or permission checking (the tool is available to all authenticated MCP clients).
- Metrics beyond the three specified fields (CPU, memory, request count, etc.).
- Caching, response time tracking, or server logging beyond standard MCP patterns.
- Integration with monitoring systems; the tool provides data only, integration is external.
- Version auto-increment; the tool reads the static version at import time.

## Constraints

- The server name must be `"oura-mcp-server"`, matching the `name` parameter passed to the FastMCP constructor in `server.py` line 30-38. [SOURCE: repo, server.py:30-38]
- The version must be read from `__version__` in `src/oura_mcp_server/__init__.py`, which is currently `"0.1.1"`. [SOURCE: repo, __init__.py:3]
- The timestamp must be in UTC and ISO 8601 format. [SOURCE: request]
- The tool must follow the existing MCP tool pattern: an async function decorated with `@mcp.tool`, returning a dict, with no external dependencies or API calls. [SOURCE: repo, server.py]
- The tool must integrate with the pytest + respx testing pattern used in `tests/test_server_tools.py`. [SOURCE: repo, tests/test_server_tools.py]

## Key entities

**ping response**: A snapshot of server identity and time, returned as a JSON object. Fields:
- `server` (string): The server's name, used by MCP clients to identify which server they are connected to.
- `version` (string): The semantic version of the package, for diagnostics and update tracking.
- `time_utc` (string): Current UTC time, used as a lightweight liveness indicator and clock synchronization check.

## Assumptions

- **A1.** The response contains exactly the three requested fields (`server`, `version`, `time_utc`), with no wrapper dict or metadata. `[SOURCE: request]` - the ticket specifies the exact JSON shape. *If wrong:* clients expecting a simple object get nested data; requires structural change to response and all tests.

- **A2.** The `time_utc` field uses Python's `datetime.isoformat()` default format (e.g., `2026-10-28T16:30:45.123456+00:00`), not a string ending in `Z`. `[SOURCE: inferred]` - the request says "ISO 8601 timestamp" but does not specify the variant; Python stdlib defaults to `+HH:MM` notation. *If wrong:* clients parsing `Z` suffix will fail; requires changing the timestamp format and updating AC5.

- **A3.** The tool will never raise an exception and has no error path. `[SOURCE: inferred]` - the tool does not call external APIs or access state that could fail, so error handling is unnecessary. *If wrong:* a test expects error-case coverage; the tool remains trivial and has only a happy path.

- **A4.** The version string is imported once at module load time from `__init__.py` and is not re-evaluated on each call. `[SOURCE: repo, server.py pattern]` - all module-level data in server.py is set once and reused. *If wrong:* version becomes dynamic; adds negligible overhead but changes the implementation pattern.

- **A5.** The `ping` tool is placed in `server.py` after the webhook subscription management tools (after line 499), before the `run()` function, as a final diagnostic tool. `[SOURCE: convention]` - tools are grouped by domain; diagnostics follow application-management tools. *If wrong:* tool is elsewhere in the file; no functional impact, readability only.

- **A6.** The tool's docstring is a single line: `"Ping the server: returns server name, version, and current UTC time."` `[SOURCE: convention]` - other simple tools have one-line docstrings (e.g., `get_personal_info` at line 239, `get_ring_configuration` at line 249). *If wrong:* docstring is longer or includes usage examples; tool help is more verbose but adds no functional value.

- **A7.** The test file is `tests/test_server_tools.py` and uses the existing `server` fixture (sets `OURA_ACCESS_TOKEN`, resets `_client`). `[SOURCE: repo, tests/test_server_tools.py]` - all existing tool tests follow this pattern. *If wrong:* test lives in a separate file; no impact on implementation, test organization only.

## Open questions

- **Q1.** Should the ping response include additional fields such as uptime, request count, or git commit SHA for more detailed diagnostics? **Proceeding as:** NO. The request specifies exactly three fields and calls it a "simple" tool. Revisit only if MCP clients request extended diagnostics in future issues.

- **Q2.** Should `server` be the FastMCP instance name (`"oura-mcp-server"`) or include deployment metadata like hostname or environment? **Proceeding as:** Just the FastMCP name, per the request's explicit definition. Deployment metadata is external to the server role.
