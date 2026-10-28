---
name: speckit-clarify
description: Resolve every ambiguity in a draft specification without a human to ask. Converts each unknown into a numbered, sourced, individually rejectable assumption, then writes the implementation plan. Use as phase 2 of planning, after specify and before tasks. Adapted from GitHub Spec Kit for headless operation.
---

# Clarify

Phase 2 of planning. Resolve ambiguity, revise `spec.md`, write `plan.md`.

> Adapted from GitHub Spec Kit's `clarify` command, which asks the user up to five
> questions and waits for answers. **You have nobody to ask.** This skill replaces asking
> with assuming-and-documenting, which moves the human interaction from mid-run to review
> time: the reviewer corrects a list instead of answering a quiz.

## Why this is the phase that matters

This process bets that a human-approved contract makes downstream review cheap. That
only holds if the human can see what you decided on their behalf. A wrong assumption that
is *written down* costs one line of review. The same assumption *unwritten* costs a wrong
implementation, a wasted review, and a rebuild.

**So: it is always better to assume loudly than to guess quietly.**

## Procedure

### 1. Sweep for ambiguity

Walk the draft spec and find every point where a competent implementer could reasonably
go two ways. Include the `[NEEDS CLARIFICATION]` markers, but do not stop there. The
dangerous ambiguities are usually the ones nobody noticed.

Check each of these categories explicitly. Most requests are silent on most of them, and
silence is where wrong assumptions live:

| Category | The question nobody asked |
|---|---|
| Scope boundary | Does this apply to all users, or a subset? |
| Data volume | What happens at 10 records? At 10 million? |
| Time semantics | "Recent": over what window? Which timezone? |
| Empty and error states | What does the user see when there is nothing, or it fails? |
| Permissions | Who is allowed to do this? Who can see the result? |
| Backwards compatibility | Does existing data or an existing API contract still work? |
| Concurrency | What if two people do this simultaneously? |
| Persistence | Is this durable, cached, or ephemeral? |

### 2. Resolve each one

Pick the most defensible reading, in this order of preference:

1. **The repo, if mounted.** Check what the system already does. Cite `path:line`.
2. **Explicit statements elsewhere in the request.** Often the answer is two sentences later.
3. **Convention for this class of system.** What would a competent team default to?
4. **The most conservative option.** When stuck, pick the choice that is cheapest
   to reverse and least surprising. This is usually the narrower scope.

### 3. Record it

Every resolution becomes a numbered assumption in `spec.md`:

```markdown
## Assumptions

- **A1.** "Recently" means the last 30 days.
  `[SOURCE: convention]`: no window given; 30d matches the existing dashboard default.
  *If wrong:* AC1's window changes. One-line fix, no structural impact.

- **A2.** Applies to authenticated users only; anonymous visitors get 401.
  `[SOURCE: repo, src/routes/export.ts:18]`: every sibling route is behind `requireAuth`.
  *If wrong:* an auth-exempt path is needed. Moderate: affects FR2 and AC2.

- **A3.** Archived records are excluded.
  `[SOURCE: inferred]`: nothing in the request addresses archived data at all.
  *If wrong:* the query predicate changes and row counts in AC1 change with it.
```

Three parts, all required:

- **The decision**, stated as fact, not as a question.
- **The source tag and the reasoning.** `[SOURCE: inferred]` is honest and expected.
  Use it whenever the other three do not apply. Do not dress a guess up as a
  convention to make the spec look better founded than it is.
- **`If wrong:`** states the blast radius. This is what lets a reviewer triage. An assumption
  whose failure costs one line gets a glance; one that invalidates the structure gets
  real attention.

### 4. Surface the riskiest three

Fill in the spec's **Riskiest assumptions** section: the three most likely to be wrong,
weighted by blast radius. This is the section a busy reviewer reads.

Rank by the chance of being wrong times the cost of being wrong, not by how uncertain you felt.

### 5. Record open questions

Flag the things you resolved where you had to choose, and the choice is material,
not obvious and cheap to revisit:

```markdown
## Open questions

- **Q1.** Should archived records be included in the export?
  **Proceeding as:** NO (see A3). Revisit if finance needs historical completeness.
```

These are **non-blocking**. You proceed regardless. They exist so the reviewer can
redirect without having to re-derive the question.

### 6. Remove every marker

No `[NEEDS CLARIFICATION]` may survive. Each is now an assumption or an open question.

## Then write `plan.md`

Now, and only now, write the implementation approach. The spec says what; this says how.

```markdown
# Plan: <N>-<slug>

## Approach
The shape of the change, in a paragraph. Why this route over the obvious alternative.

## Affected areas
Where the change lands. Cite real paths if the repo is mounted; otherwise say the repo
was not available and describe the areas by role.

## Data
Schema, migration, or state changes. "None" is a valid and welcome answer.

## Sequencing
What must happen before what, and why. Only real dependencies. Do not invent order
where none exists, or you serialize work that could run in parallel.

## Risks
What could go wrong in implementation, and the cheapest mitigation for each.

## Explicitly not doing
Approaches considered and rejected, with the reason. Prevents the implementer
re-litigating a decision you already made, and tells the reviewer you considered it.
```

## Anti-patterns

- **Assumption laundering.** Tagging a guess as `[SOURCE: convention]` because `inferred`
  looks weak. It is not weak; it is the tag that earns the reviewer's attention.
- **Questions disguised as assumptions.** "A4. The retention period is whatever
  the team prefers" decides nothing. Pick a number.
- **Missing `If wrong:`.** Without blast radius, every assumption looks equally important,
  which means none of them gets read properly.
- **Twenty assumptions.** If you have that many, the request is under-specified enough
  that the spec should say so prominently in its Summary. Consolidate the trivial ones.
