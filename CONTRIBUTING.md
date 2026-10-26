# Contributing

Thanks for your interest in improving oura-mcp-server. This is a small project with a single
maintainer, and the hosted deployment fronts a real person's health data. The process below is
deliberately cautious: it keeps unreviewed code away from that deployment and keeps the project
maintainable by one person. Please read it before you start writing code.

## Before you write code

| Kind of change | What to do |
|---|---|
| Typo, broken link, failing test, obvious one-line bug | Open a pull request directly. |
| Anything else (new tool, behaviour change, new docs section, refactor, dependency) | [Open an issue](https://github.com/sumedhkhodke/oura-mcp-server/issues/new/choose) first and wait for a maintainer "yes" before writing code. |
| Security problem | Do **not** open an issue or PR. Follow [SECURITY.md](SECURITY.md). |

Pull requests for features that were not agreed in an issue may be closed without review. That is
not a judgement of the work; it is how the project avoids taking on code nobody has agreed to
maintain.

## What's in scope

Welcome:

- New read-only tools that wrap [Oura v2 API](https://cloud.ouraring.com/v2/docs) endpoints
- Analytics improvements (`analytics.py`), bug fixes, and test coverage
- Documentation fixes and clarifications, the `/oura` skill, and the Claude Code plugin packaging
- Community deployment guides (see [below](#community-deployment-guides))

Welcome, but reviewed more slowly and strictly:

- Anything touching Oura token handling (`auth.py`, `oauth.py`, `client.py`), the GitHub OAuth
  proxy (`mcp_auth.py`), the `/webhook` route (`webhook_receiver.py`), the `Dockerfile`,
  `docker-entrypoint.sh`, or the Railway configuration. These changes must come with tests and a clear
  explanation of why they are safe.

Likely to be declined:

- Tools that write to or modify Oura health data. The server is read-only by design.
- Turning the server into a multi-user or multi-account service. It serves one Oura account.
- Telemetry, analytics, or any outbound call to a service other than Oura and GitHub OAuth.
- New runtime dependencies that were not discussed in an issue first.
- Code changes whose main purpose is supporting a specific hosting platform.

## Community deployment guides

The README's Railway section is the reference deployment: it is what the maintainer runs and can
vouch for. Guides for other platforms are welcome as **docs-only** pull requests under a
"Community deployment guides" section, on these terms:

1. **Disclose any affiliation.** If you work for, are paid by, or otherwise represent the
   platform, say so in the PR description. Affiliation is fine; undisclosed affiliation is not.
2. **Test it on a real deploy before opening the PR.** At minimum, confirm in the PR description
   that:
   - the image builds from the existing `Dockerfile` with no changes
   - the server starts with `--transport http` and the GitHub OAuth callback completes
   - a volume mounted at `/data` keeps `OURA_TOKEN_FILE` and `FASTMCP_HOME` across a restart
     (without it, a restart falls back to an already-consumed refresh token)
   - an MCP client can connect and call at least one tool
3. **Docs only.** No platform config files, no `Dockerfile` or entrypoint changes, no code paths
   for one platform. If the existing image doesn't work there, open an issue to discuss it.
4. **No secrets or personal values.** Use placeholders (`<your-app>`, `<client-id>`) for every
   credential, URL, and username.
5. **You maintain it.** Your GitHub handle goes next to the section. If it goes stale or breaks,
   you'll be tagged first; the section is removed only if it can't be brought back up to date.

## How changes reach `main`

```text
your branch ──PR──▶ staging ──maintainer PR──▶ main ──▶ tagged GitHub Release
                     (you)                    (deploys)
```

- **Open every pull request against `staging`, never `main`.** Pushes to `main` deploy
  automatically to the maintainer's hosted server. GitHub preselects `main` when you open a PR,
  so change the base branch. A required check fails any PR into `main` that doesn't come from
  `staging`; if you see it fail, edit the PR and switch the base to `staging`.
- The maintainer merges approved PRs into `staging`, batches them, and opens a `staging` → `main`
  pull request. Merging that PR is the release: it deploys, and a tagged
  [GitHub Release](https://github.com/sumedhkhodke/oura-mcp-server/releases) follows.
- Contributors never need to touch `main`, version numbers, tags, or release notes.

## Development setup

You need Python 3.10 or newer and [uv](https://docs.astral.sh/uv/). No Oura account or token is
needed to run the test suite.

```bash
git clone https://github.com/<you>/oura-mcp-server.git    # your fork
cd oura-mcp-server
git remote add upstream https://github.com/sumedhkhodke/oura-mcp-server.git
git fetch upstream
git switch -c fix/short-description upstream/staging     # branch from staging, not main

uv sync                                                    # package + dev group
uv run ruff check . && uv run ruff format --check .        # lint + format (CI gates on both)
uv run pytest -q                                           # HTTP mocked with respx
uv lock --check                                            # CI fails if uv.lock drifts
uvx pre-commit install                                     # optional: same checks on commit
```

If you want to try the server against your own ring, see the README's Quickstart. Use your own
Oura OAuth app and account.

## Conventions

**Branches**: `feat/`, `fix/`, `docs/`, or `chore/` followed by a short description.

**Commits**: an imperative, sentence-case subject under about 72 characters, for example
`Verify Oura's webhook signature on /webhook POSTs`. Explain the why in the body when it isn't
obvious. Keep one logical change per PR.

**Tools and prompts** (`server.py`):

- Register tools on the module-level `FastMCP` instance and get the client through `_get_client()`.
- Date-range tools delegate to `_collection()`, which supplies the 7-day default window.
- Parse inputs with `_parse_date` / `_parse_datetime`. Bad input and `OuraError` return an
  `{"error": ...}` dict; tools never raise to the client.
- When adding or renaming a tool, update the README tool table and the `allowed-tools` list in
  `skills/oura/SKILL.md`, where each tool appears twice (`mcp__oura__*` and
  `mcp__plugin_oura_oura__*`).

**Tests**:

- Every Oura call is mocked with `respx`. Nothing may hit the network.
- Tool tests follow the `server` fixture in `tests/test_server_tools.py`.
- Changes to token resolution need a case in `tests/test_auth.py`.
- Fixtures use synthetic data only. Never paste real Oura responses, tokens, or personal info.

**Never commit**: `.env`, `tokens.json`, OAuth client secrets, access or refresh tokens, or
anything from `~/.oura-mcp/`. If you commit one by accident, say so in the PR so it can be
rotated; force-pushing it away does not make it secret again.

**AI-assisted contributions** are fine. You are responsible for every line: you must have read
it, run the tests, and be able to answer review questions about it.

## Opening the pull request

1. Rebase on the latest `upstream/staging` and set the PR's base branch to `staging`.
2. Fill in the [pull request template](.github/PULL_REQUEST_TEMPLATE.md), including the linked
   issue.
3. Leave "Allow edits by maintainers" checked, so small fixups can be pushed to your branch.
4. CI runs lint, the lockfile check, and tests on Python 3.10 through 3.14. CI on PRs from
   first-time contributors may wait for maintainer approval before it runs.

## Review

- Review is best-effort. Expect a first response within two weeks; a polite ping after that is
  welcome.
- The maintainer may ask for changes, push small fixups, or decline a PR that is well built but
  that the project doesn't want to maintain long term.
- Approved PRs are merged into `staging`, not `main`. They ship with the next release.

## Releases (maintainer reference)

Versions follow [Semantic Versioning](https://semver.org/). While the project is `0.x`, a minor
bump covers new tools or behaviour changes and a patch bump covers fixes. Hotfixes take the same
path: merge into `staging`, then promote.

1. On `staging`, bump the version in `src/oura_mcp_server/__init__.py`,
   `.claude-plugin/plugin.json`, and `.claude-plugin/marketplace.json`.
2. Open a `staging` → `main` pull request and merge it with a merge commit (not squash), so the
   two branches don't diverge.
3. Tag the merge commit and publish the release:

   ```bash
   git switch main && git pull
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   gh release create vX.Y.Z --generate-notes
   ```

## License

By contributing, you agree that your contributions are licensed under the project's
[Apache-2.0 license](LICENSE), as described in section 5 of that license. There is no CLA.
