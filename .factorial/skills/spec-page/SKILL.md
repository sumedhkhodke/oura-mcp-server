---
name: spec-page
description: Write the one-page summary of a spec that a reviewer reads before approving it, with small focused visuals
---

# Spec page

Your first turn's `# Files` section lists the page as the file labeled Summary: its path, and the
rules it is served under. Write it there and commit it with the spec files, on the branch you
push. If the section lists no file labeled Summary, write no page. On a rework, write the page
again so that it matches the spec as it stands. This skill says what to put on it.

Help the reviewer understand the proposed change visually. Skip the preamble and keep prose
brief. For each point, pick the smallest view that makes it clear.

## What the page always has

- **The change in one paragraph.** What the ticket asked for and what the spec proposes.
- **Risks and open questions.** What the reviewer should look at first.
- **Links.** The spec files on GitHub, on the branch you push. On a rework, the spec pull request
  too: it does not exist yet when you first write the page.

Everything else is a view, placed next to the short text it supports.

## Views to choose from

- Show logic or an algorithm as pseudocode:

```text
on(save)
  if content is unchanged
    return cached result
  write new content
  return fresh result
```

- Show runtime control flow as a call tree:

```text
submitForm
  createSession
    persistPrompt
    launchAgent
  navigateToSession
```

- Show UI structure as a component tree, with the state and module boundaries that matter:

```tsx
<SessionPage> (web/src/routes/session.tsx)
  useSessionEvents()
  <SessionToolbar>
    <RunSkillButton> (packages/ui)
```

- Show which files own what, or a broad refactor, as a shallow file tree:

```text
src/
├── commands/       # parses user actions
├── sessions/       # owns session state
└── transport/      # sends API requests
```

- Use a `diff` when the point is what changes and the surrounding shape already exists. Match
  the diff to the topic, such as a component tree, a file layout, a call tree, or state and control
  flow:

```diff
 <SessionPage>
   useSessionEvents()
   <SessionToolbar>
+    <RunSkillButton />
   <SessionTimeline>
+    <SkillResultCard />
```

```diff
 on(save)
-  write content
+  if content is unchanged
+    return cached result
+  write new content
+  invalidate cache
```

- Show the whole block when most of it is new, when leaving context out would hide who owns
  what or in which order things happen, or when the reviewer needs the exact target shape.

- Show how components interact, or how control or data flows, as a diagram: a sequence, a
  data flow or a state machine. The page runs no scripts, so a Mermaid block never draws.
  On an HTML page, draw the diagram as inline SVG. In Markdown, draw it as text in a fenced
  block:

```text
User ──choose command──▶ UI ──expanded prompt──▶ Daemon
User ◀──────── result ── UI ◀──── stream ─────── Daemon
```

- For a UI layout, a comparison of states, or a concept too dense for a small diagram, give it
  a focused section of its own: an inline-SVG infographic or a sketch of the layout, with the
  product's real labels.

## Guidance

Place each view next to the short text it supports. Keep only the calls, files, props, states
and boundaries the reviewer needs to decide on this spec, or to settle the questions it leaves
open. Use real labels and real numbers. Count them from the spec and the plan, and never invent
them.

You may use one of these views or several; you will rarely use all of them. Use your judgment
and do not overwhelm the reviewer.

## How the page is built

Within the rules your `# Files` section gives:

- **HTML.** Put all CSS in a `<style>` element. Put code-shaped views in `<pre>` blocks, and
  color a diff's added and removed lines. Use `<details>` for sections a reader can open. Give
  each inline `<svg>` a `<title>`. Use the system font stack, and support light and dark with
  `prefers-color-scheme`.
- **Markdown.** Give each section a heading. Put code-shaped views in fenced blocks with their
  language (`text`, `diff`, `tsx`), and metrics in tables. The page is styled for you.
- Keep the file small: a good page is well under 200 KB.
