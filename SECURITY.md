# Security Policy

## Reporting a vulnerability

Please do not open a public issue for security problems.

Report privately via GitHub's **Report a vulnerability** button on the
[Security tab](https://github.com/sumedhkhodke/oura-mcp-server/security/advisories/new)
of this repository, or email <sumedh.khodke@gmail.com>. Include steps to reproduce,
the affected commit or version, and your assessment of impact.

You will receive a reply within 7 days. Once a fix is available, the report and
credit (if you want it) are published in the release notes.

## Scope

This server stores Oura OAuth tokens on disk (`~/.oura-mcp/tokens.json` or
`OURA_TOKEN_FILE`), refreshes them at runtime, and — in HTTP mode — fronts a
personal health account behind a GitHub OAuth allowlist. Bugs in token handling,
token persistence, the GitHub OAuth proxy or allowlist, and the `/webhook` route's
verification-token gate are all in scope, as is anything that leaks health data to
an unauthorized client.

## Supported versions

Only the `main` branch receives security fixes. Pull the latest commit or redeploy
from `main` to pick them up.
