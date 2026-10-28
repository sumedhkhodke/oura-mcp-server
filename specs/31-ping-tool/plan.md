# Plan: 31-ping-tool

## Approach

Add a single, stateless async function `ping()` to `server.py` decorated with `@mcp.tool`. The function reads two module-level constants (the FastMCP instance's name and the imported `__version__` string) and returns a dict with three fields: `server`, `version`, and `time_utc`. No external calls, no state, no error cases—a minimal diagnostic tool that tests MCP connectivity and reflects server identity.

The tool is intentionally simple and separate from the Oura data-fetching tools; it requires no client credentials and serves only as a liveness check. Its implementation is a single import statement and one 3-line function, making it a low-risk addition suitable for testing the Factorial spec-to-implementation pipeline.

## Affected areas

- `src/oura_mcp_server/server.py` (lines 500-510, before `run()` function): new `ping()` tool definition
- `src/oura_mcp_server/__init__.py` (no changes, already exports `__version__`)
- `tests/test_server_tools.py` (new test function `test_ping()`, ~10 lines)
- `README.md` (lines 48-60, tools table): one-line entry for `ping`

## Data

None. The tool is purely computational: it reads static data (server name, version string) and generates a timestamp. No database, no cache, no state mutations.

## Sequencing

All changes are independent and can be made in parallel:

1. Add `ping()` function to `server.py`
2. Add test to `tests/test_server_tools.py`
3. Update README.md tools table

Each can be completed without the others, though the test should validate the function before the README is updated.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Timestamp format mismatch (clients expect `Z` suffix) | Medium | Clients fail to parse response | AC5 pins format to Python's `isoformat()` output; reviewer catches deviations before merge |
| Tool is accidentally registered twice or conflicts with future tool names | Low | Naming collision, tool hidden in list | Tool names are explicit and unique; `ping` is unlikely to collide; simple name review in PR |
| Version import fails or returns None | Very low | Tool returns incorrect version or raises | `__version__` is always defined in `__init__.py` at build time; test verifies it is a string |
| Tool is placed in wrong file or section, making it hard to find | Very low | Documentation only; no functional impact | Placement follows existing tool-grouping conventions (diagnostics after application tools) |

## Explicitly not doing

- **Error handling / fallback paths**: The tool has no external dependencies, so there are no failure scenarios to handle. A future version might add graceful degradation (e.g., version="unknown" if import fails), but that is out of scope for this simple implementation.

- **Caching the timestamp**: The tool computes the current time on every call. Pre-computing or caching would not be meaningful for a health check; clients expect a fresh timestamp.

- **Extended diagnostics**: Uptime, request counters, git commit SHA, or deployment metadata are not included, per A1. The tool is intentionally minimal.

- **Authentication or permission gating**: The tool is available to all MCP clients, including those without Oura credentials. This is by design: a health check should not require credentials.

- **Logging or instrumentation**: The tool does not log itself or emit metrics beyond what FastMCP logs by default (tool invocation). It is too simple to warrant special instrumentation.

- **Versioning the API response**: The response format is fixed to the three fields. If we need to extend it later, a new tool (e.g., `ping_v2`) would be added; the old `ping` would remain unchanged for backward compatibility.
