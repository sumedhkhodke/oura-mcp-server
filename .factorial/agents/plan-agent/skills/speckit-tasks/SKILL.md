---
name: speckit-tasks
description: Decompose an approved plan into an ordered, dependency-aware task list where every task traces to an acceptance criterion. Use as phase 3 of planning, after specify and clarify. Adapted from GitHub Spec Kit for headless operation.
---

# Tasks

Phase 3 of planning. Produce `tasks.md`.

> Adapted from GitHub Spec Kit's `tasks` command. Upstream emits a flat checklist; this
> version requires an explicit dependency graph, because whoever builds it needs to know
> what can run concurrently and what cannot.

## What a task is

One coherent unit of implementation work. Small enough to review in a sitting; large
enough to be worth its own commit.

Sizing test: **could a competent engineer finish it in half a day, and could a reviewer
verify it without reading the other tasks?** If no to either, split it.

## Structure of `tasks.md`

```markdown
# Tasks: <N>-<slug>

## Overview
N tasks. Critical path: T1, then T3, then T5. T2 and T4 can run in parallel with T3.

## Tasks

### T1: <imperative title>
**Depends on:** none
**Satisfies:** AC1, AC2
**Done when:** <observable condition: how a reviewer confirms this task is complete>

<Two or three sentences of what to do. Enough to remove ambiguity, not so much that
it becomes the implementation.>

### T2: <imperative title>
**Depends on:** T1
**Satisfies:** AC3
**Done when:** <observable condition>

## Coverage check
| Acceptance criterion | Covered by |
|---|---|
| AC1 | T1 |
| AC2 | T1, T4 |
| AC3 | T2 |

Every AC must appear. An uncovered AC means the decomposition is incomplete.
Every task must satisfy at least one AC, or trace to a Constraint. A task
that satisfies nothing is scope creep and should be cut.

## Parallelism
Which tasks may run concurrently, and what they would collide over if they did.
This determines how many implementers can safely work at once.
```

## Dependencies

Record only **real** dependencies: T2 cannot start until T1 exists.

Do not encode preference as dependency. "I would do the API before the UI" is an opinion;
if the UI can be built against a stubbed contract, they are parallel. Spurious
dependencies serialize work that did not need serializing, and that directly
costs throughput.

Two things that *are* real dependencies and are often missed:

- **Shared-file collisions.** Two tasks editing the same file will conflict textually.
  Note it under Parallelism even if they are logically independent.
- **Contract-then-consumer.** If T2 calls an interface T1 defines, that is real,
  unless the interface is already specified precisely enough to stub, in which case say
  so and mark them parallel.

## Traceability is the point

Every task carries `Satisfies:`. This is what makes the spec a contract rather than a
description. It lets anyone check that the built thing and the agreed thing are the same
thing, without reading the diff.

If a task satisfies nothing, one of three things is true, and you should say which:

1. It is necessary infrastructure: trace it to a Constraint instead.
2. An acceptance criterion is missing: go back and add it to `spec.md`.
3. It is scope creep: cut it.

## Anti-patterns

- **Layer-shaped tasks.** "T1: write the models. T2: write the views." These maximize
  collisions and mean nothing works until everything works. Prefer vertical slices that
  each deliver an observable behavior.
- **A task per file.** File count is not work.
- **"Write tests" as a task.** Tests come from the acceptance criteria and are authored
  separately, in a place the implementer cannot edit. A task to write tests would let the
  implementer check its own work.
- **Invented ordering.** If two tasks are independent, say so. Throughput depends on it.
- **Tasks that restate the AC.** "T3: make AC3 pass" carries no information. Say what
  changes.
