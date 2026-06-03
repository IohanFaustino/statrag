# Resume digest → Facilitate document style + per-section math — Design

**Date:** 2026-06-03
**Mode affected:** `resume` (chapter pipeline, rendered by `ChapterDigestCard`)
**Status:** Approved (design), pending implementation plan

## Problem

Resume mode renders as a heavy **card-with-inner-boxes**: an outer bordered card
(secondary-accent left stripe, shadow) containing one bordered box per subtopic.
Facilitate mode renders the same `ChapterDigest` data as a **flowing document**
(no card chrome, no boxes). The user wants Resume to adopt Facilitate's
document layout, with per-element parity (citations, inline formula, headings,
page captions).

Separately, Resume currently piles **all formulas at the bottom** of the card
(card-level `digest.math_blocks`). Formulas must instead appear **inside the
section they belong to**.

## Goal

1. Resume renders with Facilitate's document chrome — no outer card, no
   per-section boxes — keeping the amber "Resume" eyebrow as its only identity
   marker. Resolution note + grounding badge stay.
2. Each section's formulas render inside that section, not in a trailing pile.

## Non-goals

- No change to chapter pipeline logic, stage order, or prompts.
- No change to `tutorPipeline.ts` / `PipelineDiagram` (no stage added/changed).
- No change to Facilitate behaviour.
- No change to citation semantics — only how Resume's container is styled.

## Root cause (per-section math)

`map_sections` (`src/services/chat/agents/chapter.py:235`) already computes each
section's `math` from the `ChapterMapBlock` LLM output, but builds the
`ChapterBlock` **without** it (line 240) and flattens all math into card-level
`digest.math_blocks`. Per-section rendering requires threading that math onto the
block.

The Resume body renderer `renderInlineWithCites` (`web/src/components/views/TutorView.tsx`)
**already** renders inline `$…$` and block `$$…$$` math and `[n]` citation
superscripts. So per-element parity (citations, inline formula) needs **no**
renderer change — only the container/box CSS and the per-block math wiring change.

## Design

### 1. Layout / CSS — `web/src/styles/chapter.css`

`.chapter-card--facilitate` already strips card chrome (no border/bg/shadow,
padding 0), makes the header a hairline separator, and renders box-less sections
with flowing accent headings. Bring `.chapter-card--resume` under the same
treatment:

- Refactor the chrome-stripping and box-stripping rules so the selectors apply to
  **both** `.chapter-card--facilitate` **and** `.chapter-card--resume` (shared
  rule list — no copy-paste duplication).
- Remove from Resume: the outer card border/shadow/bg, the `border-left` accent
  stripe (`.chapter-card--resume`), and the bordered `.chapter-block` box
  (bg-secondary, border, left red stripe) — sections become heading + page
  caption + flowing prose with the same spacing as Facilitate.
- Keep `.chapter-card--resume .chapter-card__mode` amber-eyebrow rule as the sole
  Resume identity marker.
- Resume body keeps justified-vs-left as Facilitate (`line-height: 1.6`,
  left-aligned) so prose reads identically. (Drop the Resume-only
  `text-align: justify`.)

### 2. Per-section math — data model

- **Backend schema** `src/services/chat/schemas/output.py` `ChapterBlock`
  (line ~310): add `math_blocks: list[str] = Field(default_factory=list)`.
- **Backend** `src/services/chat/agents/chapter.py` `map_sections` (line ~240):
  pass `math_blocks=math` into the `ChapterBlock(...)`. Card-level
  `digest.math_blocks` stays populated (back-compat) but is no longer the render
  source.
- **Frontend type** `web/src/types.ts` `ChapterBlock` (line ~177): add
  `math_blocks?: string[]`.
- **Frontend render** `web/src/components/ChapterDigestCard.tsx`: after each
  section's `<div className="chapter-block__body">`, render that block's
  `math_blocks` via `<MathBlock>` (same component already used). **Remove** the
  trailing card-level `digest.math_blocks` pile.

**Decision (math mechanism):** explicit per-block `math_blocks` field rendered as
`<MathBlock>` under each section. Rejected alternative: injecting `$$…$$` into the
block `body` string (risks double-render when the model already embeds math; not
testable in isolation).

### 3. Export — out of scope

`exportStructured.ts` has **no** `ChapterDigest` formatter — resume export falls
through to the `default` raw-JSON dump (`structuredToMarkdown`, line ~77). There
is nothing to "move": the trailing `### Math` block belongs to `qa()`, not
resume. A proper resume export formatter is net-new work unrelated to the visual
remake, so it is **excluded** from this design (YAGNI). Resume export stays a raw
JSON dump.

## Data flow

```
ChapterMapBlock (LLM, per section) ──> math: list[str]
   │  (chapter.py map_sections)
   ▼
ChapterBlock.math_blocks  ──(model_dump)──>  SSE structured_output
   │
   ▼
types.ChapterBlock.math_blocks ──> ChapterDigestCard renders <MathBlock> per section
                               └──> exportStructured.resume() emits $$…$$ per section
```

Order invariant unchanged: block list order = chapter section order; math renders
with its block, so math order follows section order for free.

## Error handling

- `map_sections` already fails open (`body, cites, math = excerpt, [], []` on
  exception) — empty `math_blocks` renders nothing. Unchanged.
- `math_blocks?` optional on the frontend type → old persisted digests without
  per-block math render with zero section math (no crash); card-level
  `digest.math_blocks` remains in the payload for any legacy consumer.

## Testing

- **Backend** (`src/services/chat/tests/`): extend the chapter map test —
  `map_sections` returns blocks whose `.math_blocks` carries that section's LaTeX
  (mock `_chat` to return `{"math_blocks": ["x^2"], ...}` for one section, assert
  it lands on the right block, not flattened away).
- **Frontend** (`web/src/components/ChapterDigestCard.test.tsx`):
  - resume digest with a block carrying `math_blocks` renders a `MathBlock`
    inside that section;
  - resume card has **no** bordered `.chapter-block` box and **no** outer card
    border (assert the facilitate-style class wiring / computed absence);
  - no trailing card-level math pile element.

## Lockstep artifacts touched

| Artifact | File |
|---|---|
| Schema | `src/services/chat/schemas/output.py` (`ChapterBlock`) |
| Backend wiring | `src/services/chat/agents/chapter.py` (`map_sections`) |
| Frontend type | `web/src/types.ts` |
| Frontend render | `web/src/components/ChapterDigestCard.tsx` |
| CSS | `web/src/styles/chapter.css` |
| Tests | chapter backend test, `ChapterDigestCard.test.tsx` |
| Per-feature doc | `docs/services/chat-features/53-*.md` (note layout change) |

Not touched: prompts, `tutorPipeline.ts`, `PipelineDiagram.tsx`, pipeline graph
docs (no stage change).

## Verification

After implementation, open `:5175`, run a Resume turn (e.g. "resume hansen ch7"),
confirm: document layout (no boxes), formula renders inside its section, amber
eyebrow present, grounding badge + resolution note intact. Compare against a
Facilitate turn for chrome parity.
