# Chat Markdown Export — Design

**Date:** 2026-05-29
**Agent:** system_Agent (frontend-only; no backend, no pipeline)
**Status:** design, pending build

## Goal

Let a user export chat content as a `.md` file at two granularities:

1. **Full active conversation** — a download button in the Topbar.
2. **Single answer** — a small export icon at the end of each assistant message.

Pure frontend: the transcript already lives in the client store (`web/src/state/chat.ts`). No backend route, no SSE change, no schema change. Chinese wall untouched (no `src/` change at all).

## Decisions (locked with user)

- **Scope:** Topbar = full conversation; per-answer icon = that one answer.
- **Single-answer content:** answer body **only** — do NOT prepend the triggering question.
- **Detail level:** faithful/full — text, math (`$$tex$$`), figures, sources/citations, and a small header.
- **Structured modes:** **faithful markdown** per schema (not a JSON dump).

## Architecture

One new pure module + two thin UI wirings + one handler pair in `App.tsx`.

```
web/src/lib/exportMarkdown.ts      NEW — pure serializer + download helper
web/src/components/Topbar.tsx      + download button (onExportConversation)
web/src/components/MessageThread.tsx + per-answer icon (onExportMessage)
web/src/App.tsx                    wire both handlers to active slice
web/src/lib/exportMarkdown.test.ts NEW — vitest unit tests
```

### Module: `exportMarkdown.ts`

All functions pure (no React, no DOM except the download helper). Importable and unit-tested in isolation.

```ts
// Public surface
export function assistantMessageToMarkdown(msg: AssistantMessage): string;
export function userMessageToMarkdown(msg: UserMessage): string;
export function conversationToMarkdown(
  messages: Message[],
  meta: { title: string; date?: string },
): string;
export function slugify(s: string): string;
export function downloadMarkdown(filename: string, content: string): void;
```

**`assistantMessageToMarkdown`** — branches on content shape:

- If `msg.structuredOutput` present → dispatch on `schema`:
  - `TutorAnswer` → prose `text` (math normalized to `$$…$$`), then a `### Citations` numbered list from `citations[]`, then figures.
  - `Quiz` → numbered questions, lettered options, **Answer:** line, rubric, difficulty, source citation.
  - `NavigationList` → table: book · chapter · section · title · score.
  - `DAG` → `### Nodes` list, `### Edges` list (`from → to (weight)`), `cycles_broken` note.
  - `Report` → per-claim block with stance, evidence citations, confidence; then `### Synthesis`, `### Coverage gaps`.
  - `StudyPlan` → goal, per-week table (week · sections · hours), coverage gaps.
  - `Roadmap` → topic, per-scene block (title, concept, visual, duration, figure), total minutes.
  - `AnnotatedReading` → per-annotation: term — definition (+ source).
  - unknown schema → fenced ```json fallback (defensive, should not happen).
- Else → walk `msg.blocks`:
  - `p` → paragraph text (skip empty).
  - `math` → `$$\n<tex>\n$$`.
  - `figure` → `> **Figure** ref — caption (book · chapter)` + image link if `chart` is a URL/path.
  - `sources` → inline chip list `[book · section]`.
- Skip messages with `status` `pending`/`streaming`/`error` when serializing a full conversation (only `complete`); for single-answer export of an errored/streaming message, emit a short note rather than crashing.

**`conversationToMarkdown`** — header then turns:

```md
# <title>

> Exported from statrag · <date>

---

## You · <time>
<user text>

## <MODE> · <model> · <time>
<assistant markdown>

---
```

**`downloadMarkdown`** — `new Blob([content], {type:"text/markdown"})`, object URL, temporary `<a download=filename>`, click, revoke URL. The only DOM-touching function; excluded from pure unit tests (covered by browser-verify).

**`slugify`** — lowercase, strip non-alnum to `-`, collapse repeats, trim, cap length ~40.

### UI wiring

- **Topbar.tsx**: new `onExportConversation?(): void` prop + an `icon-btn` with a download glyph in `topbar__right`, placed immediately to the **left of the theme toggle**. Disabled when the active thread is empty.
- **MessageThread.tsx**: new `onExportMessage?(idx: number): void` prop threaded to `AssistantMessageView`; render a small icon button beside the existing `msg__fork` button. Only shown for `complete` messages.
- **App.tsx**:
  - `handleExportConversation()` → `downloadMarkdown(\`statrag-${slug}.md\`, conversationToMarkdown(messages, {title}))`.
  - `handleExportMessage(idx)` → `downloadMarkdown(\`statrag-${slug}-a${n}.md\`, assistantMessageToMarkdown(messages[idx]))`.
  - `slug` from active conversation title; `n` = 1-based index of that answer among assistant messages.

### Filenames

- Full: `statrag-<convslug>.md`
- Single: `statrag-<convslug>-a<NN>.md` (NN = answer ordinal, zero-padded 2)

## Data flow

```
User clicks export
  → App handler reads active slice messages (already in memory)
  → exportMarkdown serializer (pure)
  → downloadMarkdown (Blob → anchor click)
  → browser saves .md
```

No network. No state mutation.

## Error handling

- Empty conversation → Topbar button disabled (no-op).
- Streaming/pending/errored single message → serializer emits a `> _(answer incomplete)_` note instead of throwing.
- Unknown structured schema → JSON fallback fence (no crash).
- Blob/anchor failure → caught, `console.warn`; best-effort like `persist.ts`.

## Testing

**vitest** (`exportMarkdown.test.ts`) — pure functions:
- block prose: paragraphs + `**bold**` preserved.
- math block → `$$…$$`.
- figure block → caption line.
- sources block → chip list.
- `TutorAnswer` → prose + citations section.
- `Quiz` → numbered questions + answer line.
- `StudyPlan` → week table (second structured schema for coverage).
- full conversation → header + both turns, correct order.
- regression guard: pending/streaming message skipped in full export; empty `p` blocks dropped.
- `slugify` edge cases (spaces, punctuation, length cap).

**typecheck:** `cd web && npx tsc --noEmit` green.

**Browser-verify (Chrome MCP, :5175):**
- Send a tutor question, wait for complete answer.
- Click per-answer export icon → open downloaded `.md`, confirm answer text + citations present, no JSON leakage.
- Click Topbar download → confirm full transcript with header + both turns.
- Switch a mode that yields structured output (e.g. quiz) and confirm faithful markdown.
- Monitor console for errors during the run.

## Docs to update on completion (system_Agent interconnect)

- `docs/services/chat.md` — note the export capability (operational contract).
- `docs/system/changelog.md` — dated entry with verified result.
- `docs/common ground/Elements/index.html` — §N for the export feature, pill flipped to ✓ when verified.
- No new invariant unless we treat the filename/format as a durable contract (decide at completion).

## Out of scope (YAGNI)

- Backend export endpoint / "export all conversations".
- PDF/HTML export.
- Clipboard copy (could be a trivial follow-up reusing the serializer).
- Re-importing markdown.
