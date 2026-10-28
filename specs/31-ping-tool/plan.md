# Plan: 31-ping-tool

## Approach

Add a lightweight, no-dependency MCP tool to `server.py` that returns server metadata without making any API calls or requiring credentials. The tool is completely stateless and serves as a connectivity check for MCP clients. This is implemented as a single async function decorated with `@mcp.tool`, following the exact pattern of every existing tool in the server.

The tool does not use `_get_client()` or any authentication logic, avoiding the overhead and potential failure modes of OAuth refresh. It simply reads the MCP instance name (`mcp.name`), imports the package version from `__init__.py`, and returns the current UTC timestamp. The response is a plain JSON object with three fields: `server`, `version`, and `time_utc`.

## Affected areas

- **`src/oura_mcp_server/server.py`** (lines ~500–520): Add the new `ping` MCP tool function after the webhook tools and before the `run()` function. Place it in a new section headed with a comment `# System / health check`.

- **`tests/test_server_tools.py`** (new test, ~15–20 lines): Add one async test function that calls `ping()` and asserts the response contains all three fields with the correct types and formats. Use the existing `@respx.mock` and `server` fixture pattern.

- **`README.md`** (lines 48–66, in the tools table): Add one row to the tools table listing `ping` as "Server connectivity check: name, version, and current UTC time". Place it as the first row in the table or in a dedicated system/connectivity section.

- **`src/oura_mcp_server/__init__.py`**: No changes; version is already defined and will be imported by the tool.

## Data

None. The tool generates data at invocation time and does not read or write any persistent state.

## Sequencing

These changes are independent and can be implemented in any order:

1. Add the `ping()` function to `server.py`. This is the core implementation and can be tested immediately.
2. Add the unit test to `tests/test_server_tools.py`. This verifies the tool works correctly.
3. Update the README. This is last because it is cosmetic and can always be done later if needed.

No other changes depend on the ping tool, and no other code needs to be updated for it to work.

## Risks

- **Version import may fail at runtime**: If `__version__` is not available or misspelled, the tool will fail. *Mitigation*: Test immediately after adding the tool; the test will catch any import errors.

- **Timezone conversion errors**: If `datetime.now(timezone.utc)` or `.isoformat()` produces an unexpected format, clients may not parse the timestamp. *Mitigation*: The test should assert that the timestamp can be parsed as ISO 8601; use `datetime.fromisoformat()` in the test to verify round-trip compatibility.

- **Tool registration timing**: If the tool is defined after the `mcp` instance is finalized (unlikely in this codebase), it won't be registered. *Mitigation*: Place it in the same module as all other tools and follow the exact same pattern. The test will catch this.

## Explicitly not doing

- **Caching or persisting the version or name**: Every call generates a fresh timestamp; this is correct for a connectivity check. We do not cache metadata.

- **Adding a separate module or utility function**: The tool is simple enough to inline in `server.py` without helpers.

- **Modifying the Oura client or auth systems**: The tool is completely independent of authentication.

- **Adding optional parameters or arguments**: The requirement is "takes no arguments"; we do not add complexity.

- **Returning error dicts on failure**: The tool cannot fail in normal operation (version is a constant, datetime is always available). If something impossibly fails, it is better to raise an exception so it surfaces clearly rather than returning `{"error": "..."}`.

- **Integrating with the skill or Claude Code plugin**: The tool works automatically once registered with FastMCP; no skill changes are needed. Plugin integration can be added later if desired.
