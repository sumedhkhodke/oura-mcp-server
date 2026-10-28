# Tasks: 31-ping-tool

## Overview

3 tasks. Critical path: T1 (implement ping), then T2 (test ping) and T3 (update README) in parallel.

## Tasks

### T1: Implement `ping()` tool in `server.py`
**Depends on:** none
**Satisfies:** AC1, AC2, AC3, AC4, AC5, AC9, AC10
**Done when:** The function is defined in `server.py` between lines 500-510 (before the `run()` function), decorated with `@mcp.tool`, accepts no arguments, and returns a dict with keys `server`, `version`, and `time_utc` containing the correct values and types.

Add a new async function `ping()` to `src/oura_mcp_server/server.py` that:
- Imports `__version__` from the package `__init__.py` at module level (or inside the function)
- Reads the FastMCP instance name `mcp.name` (which is `"oura-mcp-server"`)
- Generates the current UTC timestamp using `datetime.now(timezone.utc).isoformat()`
- Returns a dict with the three fields: `{"server": "<name>", "version": "<version>", "time_utc": "<timestamp>"}`
- Has a one-line docstring describing it as a server health check

Acceptance criteria AC3, AC4, and AC5 verify the field values; AC9 verifies no external calls are made (no HTTP requests to Oura API); AC10 verifies the docstring documents it as stateless and needing no credentials.

### T2: Write unit test for `ping()` in `tests/test_server_tools.py`
**Depends on:** T1 (the function must exist to be tested)
**Satisfies:** AC6, AC7
**Done when:** A test function `test_ping()` exists in `tests/test_server_tools.py`, uses the existing `server` fixture, calls `await server.ping()`, and asserts that the response is a dict containing the keys `server`, `version`, and `time_utc` with correct types (all strings for the fields, and time_utc parseable as ISO 8601). The test does not hardcode expected values for `version` or `time_utc`.

Use the existing test pattern from `test_server_tools.py` (the `server` fixture sets `OURA_ACCESS_TOKEN` and resets `_client`). The test should verify the response shape and types, but not assert specific version strings or timestamps, so it remains stable across deployments.

### T3: Update README.md tools table
**Depends on:** none (can run in parallel with T2)
**Satisfies:** AC8
**Done when:** The tools table in `README.md` (lines 48-60, under the `## Tools` heading) includes a new row for `ping`. The row should list the tool name and a one-sentence description of its purpose (e.g., `ping` | Server health check: returns server name, version, and current UTC time).

Locate the tools table in the README and add the `ping` tool entry. The description should make clear that the tool requires no arguments and is a lightweight diagnostic for MCP connectivity.

## Coverage check

| Acceptance criterion | Covered by |
|---|---|
| AC1 | T1 |
| AC2 | T1 |
| AC3 | T1 |
| AC4 | T1 |
| AC5 | T1 |
| AC6 | T2 |
| AC7 | T2 |
| AC8 | T3 |
| AC9 | T1 |
| AC10 | T1 |

Every acceptance criterion is covered.

## Parallelism

**T2 and T3 can run in parallel** after T1 is complete:
- T2 modifies `tests/test_server_tools.py`
- T3 modifies `README.md`
- No shared files, no blocking dependencies

**T1 must complete first** because:
- T2 (test) needs the `ping()` function to exist and be importable
- T3 (README) should only document a tool that has been implemented and tested, but logically it could be written before or after

**Recommended order:** T1 → (T2 and T3 in parallel). If a single implementer, the order is T1, T2, T3, with no parallelism.

## Implementation notes

- The `ping()` function should be short (~5 lines of code) and placed before the `run()` function in `server.py` for organizational clarity.
- Import `from datetime import datetime, timezone` at the top of `server.py` if not already present (it is, at line 16).
- The version import can be added at module level as `from . import __version__` or read inside the function; module-level is conventional (see A4).
- The test does not require mocking or external fixture setup beyond the existing `server` fixture; the function is pure and has no side effects.
- No changes to other files (like `pyproject.toml`, `setup.py`, or the MCP skill SKILL.md) are required for this simple addition.
