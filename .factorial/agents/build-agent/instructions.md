# Build agent instructions

Operational context. The orchestrator verified the spec pull request (PR) merged before starting you.
It will verify your output against the process postconditions (the branch and the PR; a separate
test step checks CI after you), and it owns all labels, assignment and promotion.

## Task input

Your task names the ticket number `<N>` and the spec directory `specs/<N>-<slug>/`. The
spec is on `staging`: your workspace is a checkout of the repository with the approved spec
already in it.

Project rule: every PR targets `staging`. Never open a PR against `main` and never push to `main`.

## Workspace

```bash
git checkout -b impl/<N>-<slug> origin/staging
```

Read `AGENTS.md` before you write code. It carries the repo's invariants: build and test
commands, and the rules that are easy to violate without noticing.

## Deliver: branch, commit, push, PR

The run is not complete until a PR exists. Your token and container end at the hour.
Deliver well before that.

Commit in focused commits with real messages; the reviewer reads them alongside the diff.

```bash
git add <only the files you changed>
git -c user.name="lil-factorial[bot]" \
    -c user.email="313085768+lil-factorial[bot]@users.noreply.github.com" \
    commit -m "<One-line summary of the change>

<What changed, the approach, and the alternative you rejected, if any.>

Factory-Stage: build"

git push -u origin impl/<N>-<slug>
gh pr create --base staging --title "[Issue #<N>] Build: <one-line outcome>" --body-file /tmp/pr-body.md
```

Commit only files you changed: no lockfile churn, no build output, no incidental
reformatting. Set the identity per command with `-c`, never with `git config`.

**PR body. Write it for a reviewer who reads the diff but not the spec:**

```markdown
> Opened by Factorial's build agent. The commit trailer `Factory-Stage: build` records the stage.

## What this is
<Two sentences: the change, and the approach taken.>
This pull request implements the approved spec in `specs/<N>-<slug>/`.

## Acceptance criteria (self-assessment)
AC1 implemented. AC2 implemented. AC5 is not mechanically checkable: it needs human judgment.

## What I could not verify
<Anything you could not run, prove or determine. Write "Nothing" only if that is true.>

Closes #<N>.
```

Opening the PR is where your authority ends: never merge, never self-approve, never add
labels. CI runs on your PR, but a separate test step, not this run, waits on it and
posts the verdict. The orchestrator routes your PR to testing next, then to human review.

## Revision: you were sent back

When your inputs include a `## pr_review_comments` section, you are revising earlier work:
a reviewer requested changes on your earlier PR. Their feedback is in that section in full.
Address every point, and do not reintroduce what it flagged. (The section can be empty when
the rejection carried no comment text; the revision rules below still apply.)

Build on the delivered branch, not a fresh one:

```bash
git fetch origin && git checkout impl/<N>-<slug>
```

New commits on top. **Never rewrite published history**: no rebase, no squash, no
`--amend` and no force-push. The inline review comments are anchored to those exact commits.
