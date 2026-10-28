---
name: speckit-specify
description: Turn a raw feature request into a specification of outcomes (user scenarios, functional requirements and mechanically checkable acceptance criteria). Use as phase 1 of planning, before clarifying ambiguity or decomposing into tasks. Adapted from GitHub Spec Kit for headless operation.
---

# Specify

Phase 1 of planning. Produce `spec.md`.

> Adapted from GitHub Spec Kit's `specify` command. The upstream version pauses to ask
> the user questions. This one cannot, because there is no human in the session. Unresolved
> points are carried forward as `[NEEDS CLARIFICATION]` markers for the `speckit-clarify`
> phase to resolve into assumptions.

## The one rule

**Specify the outcome, not the implementation.**

A spec says what must become true. It does not say which library, which file, or which
pattern. That is `plan.md`'s job, and constraining it here removes the implementer's
ability to find a better route.

The test: could two competent engineers satisfy this spec with entirely different code?
If no, you have over-specified.

Exception: when the requester or the existing codebase constrains the choice
("must stay on the current auth provider"), that is a real requirement. Record it under
Constraints, with its source.

## Structure of `spec.md`

```markdown
# <N>-<slug>: <one-line outcome>

**Status:** draft, awaiting human review
**Source:** <issue #N | pasted request>
**Codebase access:** yes | NO (spec written without reading the repo)

## Summary
Two or three sentences. What changes for whom, and why it matters.

## Riskiest assumptions
The three assumptions most likely to be wrong, by number, so a reviewer who reads
nothing else reads these. (Fill this in during the clarify phase.)

## User scenarios
Concrete narratives, not abstractions. Each names an actor, a situation, and an
observable outcome.

1. **<Actor> <does something>.** Given <situation>, when <action>, then <outcome>.

## Functional requirements
Numbered, testable, one behavior each.

- **FR1.** The system MUST <requirement>.
- **FR2.** The system MUST <requirement>.

Use MUST for required, SHOULD for preferred-but-not-gating. A SHOULD never becomes
an acceptance criterion.

## Acceptance criteria
The contract. Each one becomes an automated test, fixed before implementation begins and
not the implementer's to edit. Each MUST be mechanically checkable, or explicitly marked as
not.

| # | Criterion | Verifies |
|---|---|---|
| AC1 | `GET /export?days=30` returns 200 and a CSV body with a header row | FR1 |
| AC2 | `GET /export?days=abc` returns 400, never 5xx | FR2 |
| AC3 | [NOT MECHANICALLY CHECKABLE] Export column order reads naturally to a finance user | FR3 |

## Out of scope
What this explicitly does not cover. Prevents scope creep in Build, and prevents a
reviewer assuming something is missing when it was excluded on purpose.

## Constraints
Real limits: compatibility, data, performance, regulatory. With sources.

## Key entities
Only if the change introduces or alters domain concepts. Name and describe them, without
schemas or field types. Those belong in the plan.

## Assumptions
(Filled in by the clarify phase. Leave the heading here.)

## Open questions
(Filled in by the clarify phase. Leave the heading here.)
```

## Marking ambiguity

When something is unclear, mark it inline and move on. Do not stop, and do not
silently pick:

```
- **FR3.** The system MUST retain export history for [NEEDS CLARIFICATION: retention
  period not specified (30d, 1y or indefinite?)].
```

The `speckit-clarify` phase resolves every one of these into a numbered assumption. A
`[NEEDS CLARIFICATION]` marker surviving into the final spec is a defect.

## Anti-patterns

- **Restating the request as requirements.** "The user wants X" is not a requirement.
  "The system MUST X, verified by Y" is.
- **Unfalsifiable criteria.** If no test could fail it, it is not a criterion.
- **Smuggling in design.** "MUST use a Redis cache" is a plan decision unless the
  requester or the codebase mandates it.
- **One requirement doing three things.** Split it. Each acceptance criterion should map
  to one requirement and one test.
