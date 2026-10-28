# Tasks: 31-ping-tool

## Overview

Three tasks. Critical path: T1 (implement tool), then T2 (test), then T3 (document). T2 strictly depends on T1. T3 could run in parallel with T1 but logically follows it.

## Tasks

### T1: Implement the ping MCP tool in server.py

**Depends on:** none  
**Satisfies:** AC1, AC3, AC4, AC5, AC6, AC7  
**Done when:** The `ping` tool is defined in `src/oura_mcp_server/server.py`, decorated with `@mcp.tool`, takes zero arguments, and when called returns a JSON object with `server` (value: "oura-mcp-server"), `version` (value: the string from `__init__.py`), and `time_utc` (value: current UTC time as ISO 8601).

Add the `ping()` async function to `server.py` after the webhook tool definitions (around line 500). Follow the exact pattern of existing tools: decorate with `@mcp.tool`, add a docstring, return a dict with the three required fields. Import `datetime` and `timezone` from the `datetime` module. The function should not call `_get_client()` or touch the Oura API. The tool is now discoverable by MCP clients and callable without arguments.

### T2: Write unit test for the ping tool

**Depends on:** T1  
**Satisfies:** AC2, AC8  
**Done when:** A test function exists in `tests/test_server_tools.py` that calls the `ping()` tool and asserts: (1) the response is a dict, (2) it contains exactly three keys: `server`, `version`, `time_utc`, (3) each field is a non-empty string, (4) `server` equals "oura-mcp-server", (5) `version` is a valid semver-like string, and (6) `time_utc` is parseable as an ISO 8601 UTC datetime.

Add an async test function (e.g., `async def test_ping(server)`) using the existing `server` fixture and `@respx.mock` decorator pattern. The test does not need to mock HTTP because the tool makes no API calls. Verify the response shape and all three fields.

### T3: Update README to document the ping tool

**Depends on:** T1  
**Satisfies:** AC9  
**Done when:** The README.md tools table includes a row for `ping` with a one-line description. The row lists it as available (e.g., "Server connectivity check: returns server name, version, and current UTC time").

Add a row to the tools table in README.md (lines 48–64). Place it as the first row or in a dedicated "System" section if desired. The description should be brief and clarify that it needs no arguments and makes no Oura API calls.

## Coverage check

| Acceptance criterion | Covered by |
|---|---|
| AC1 | T1 (tool implementation returns JSON) |
| AC2 | T2 (test asserts exactly three fields) |
| AC3 | T1 (server field set to "oura-mcp-server") |
| AC4 | T1 (version field reads from __init__.py) |
| AC5 | T1 (time_utc field is ISO 8601 UTC datetime) |
| AC6 | T1 (tool function takes zero arguments) |
| AC7 | T1 (@mcp.tool decorator registers tool in server's tool list) |
| AC8 | T2 (test validates response shape and all three fields) |
| AC9 | T3 (README row lists the ping tool) |

Every acceptance criterion is covered. Every task satisfies at least one criterion.

## Parallelism

**T1 and T3 can run in parallel.** Both independently modify different files (server.py vs. README.md) and have no shared file collisions or interface contracts. T3 is documentation and does not require T1 to complete first, though it makes logical sense to document after implementing.

**T2 strictly depends on T1** because it tests the tool implementation. There is no workaround: the test needs the actual tool function to exist in the imported module.

**Optimal work division:** Two developers could implement T1 (tool) and T3 (README) in parallel, then one or both run T2 (test) after T1 is complete. Or, serially: T1 → T2 → T3. Both are efficient.
