# Tutor Render And Citation Pendings Design

## Goal

Fix the three active tutor pendings together:

1. formal statement / definition boxes render with valid markdown and KaTeX-friendly math,
2. inline citation numbers match the Sources panel entries,
3. citation pills always open and scroll to the correct source row.

The fix should be minimal, keep the backend authoritative for numbering, and avoid adding new rendering machinery.

## Scope

In scope:

- `src/services/chat/agents/deep_tutor.py`
- `src/services/chat/prompts/deep_tutor.py`
- `web/src/components/views/TutorView.tsx`
- `src/services/chat/schemas/output.py` only if a small contract tightening is required
- focused backend/frontend tests covering the three regressions
- browser verification on `:5175`

Out of scope:

- redesigning tutor mode layout
- replacing the dependency-free markdown renderer
- changing unrelated deep-tutor pipeline stages
- adding a general markdown library

## Current Problems

### 1. Formal statement markdown is fragile across assembly and rendering

The current formal statement path is:

- verbatim statements are rendered in `_render_formal_statements`,
- inserted into the `formal_statement` aspect in `_convert_to_tutor_answer`,
- concatenated by `assemble_markdown`,
- reparsed by `TutorView.splitIntoBlocks`.

Recent definition-recovery work means this path now matters more often. The current blockquote output is line-oriented and fragile: blank-line handling and block boundaries are easy to break, which leads to raw `>` leakage, collapsed paragraphs, or math blocks not getting isolated cleanly.

### 2. Citation numbering can drift if derived from anything other than final text order

The intended contract is:

- backend binds `[[c:<chunkId>]]` placeholders to `[N]`,
- `TutorCitation.index` is the same `N`,
- frontend renders pills and source rows from that shared numbering.

If numbering is affected by per-aspect handling before the final markdown is assembled, or if any later stage implicitly assumes array order instead of `index`, inline markers can mismatch their corresponding source rows.

### 3. Hyperlinks fail when anchor behavior depends on anything except `index`

The frontend already uses `#cite-N` and source rows with `id="cite-N"`, but the behavior must be robust when:

- the same citation is clicked repeatedly,
- the sources panel is still closed,
- a citation number exists in text but not in `data.citations`,
- source ordering differs from array position assumptions.

## Desired Contract

### Backend contract

- `TutorAnswer.text` is the final tutor markdown to render.
- All tutor citations in `text` are already bound as `[N]` markers.
- `TutorAnswer.citations` contains one entry per bound citation.
- `TutorCitation.index` is the sole numbering authority.
- Source panel rendering and hyperlinking are based on `index`, never array position.

### Frontend contract

- `splitIntoBlocks` parses the supplied markdown-ish text without renumbering or reinterpreting citations.
- `renderInlineWithCites` uses `Map<number, TutorCitation>` keyed by `index`.
- Clicking `[N]` opens the Sources panel and scrolls to `#cite-N`.
- Missing citation objects degrade safely without breaking the rest of the answer.

## Recommended Approach

Fix the contract at the boundaries, not by adding repair layers.

### A. Make formal statements emit stable markdown blocks

`_render_formal_statements` should emit blockquote markdown that survives assembly and parsing predictably.

Requirements:

- each formal statement block stays self-contained,
- blank lines between blocks are explicit,
- display math inside statements remains visible to the frontend block parser,
- no duplicate citation suffixes are appended if the verbatim statement already carries placeholders.

This should stay in the existing function, not a new renderer.

### B. Bind citations from the final assembled tutor text once

The final assembled markdown should be the source of truth for citation ordering.

Requirements:

- no per-aspect or post-frontend renumbering,
- first appearance in final text determines `N`,
- `TutorCitation.index` values exactly match the rendered `[N]` markers,
- unresolved placeholders are removed, counted, and never guessed.

### C. Tighten the frontend block parser, not replace it

`TutorView.splitIntoBlocks` should be adjusted only enough to respect structural boundaries already present in the text.

Requirements:

- blockquotes flush correctly when lists, headings, math, images, or blank lines start,
- paragraphs do not swallow formal-statement blockquote markers,
- display math still becomes `MathBlock`,
- existing lightweight parsing model stays intact.

### D. Keep citation linking strictly index-based

`TutorView` should continue to derive all source-row ids and click handling from `TutorCitation.index`.

Requirements:

- clicking a pill for an existing citation always opens the panel,
- repeated clicks on the same pill still scroll,
- no logic depends on the citation's array offset,
- if `index` is absent from `data.citations`, the click is a safe no-op.

## Alternatives Considered

### 1. Frontend-only repair

Rejected as the main approach. It would hide backend drift and make the UI responsible for fixing malformed source data.

### 2. Backend-only canonicalization with a fully dumb frontend

Not chosen for this pass. It is directionally clean, but this branch already has active definition-recovery work and the parser still needs small structural fixes to respect the emitted markdown.

### 3. Add a real markdown library

Rejected. Too large for these bugs, changes the rendering model, and violates the repo's current lightweight approach without a stronger need.

## Files And Responsibilities

### `src/services/chat/agents/deep_tutor.py`

- keep final tutor-answer assembly authoritative,
- normalize formal statement markdown shape,
- ensure citation binding happens over the final assembled text,
- preserve audit metadata for unresolved citations.

### `src/services/chat/prompts/deep_tutor.py`

- keep `assemble_markdown` simple,
- only adjust separation rules if inspection proves special blocks need stronger blank-line boundaries.

### `web/src/components/views/TutorView.tsx`

- parse formal-statement markdown boundaries correctly,
- render inline citation pills using `index` lookups,
- open/scroll Sources robustly for repeated clicks and deep links.

### `src/services/chat/schemas/output.py`

- remains the contract source for `TutorCitation.index`,
- only change if a tiny validation rule is needed to prevent invalid index values.

## Error Handling

- unresolved `[[c:<chunkId>]]` placeholders are removed and counted in backend audit metadata,
- frontend pills only activate scroll/open when a matching `TutorCitation.index` exists,
- missing matches do not crash rendering and do not trigger fake renumbering,
- no best-effort source guessing is introduced.

## Testing Strategy

### Backend tests

Add or update tests that prove:

- formal statement markdown is emitted with stable blockquote structure,
- citation numbering follows first appearance in final assembled text,
- the `citations` payload indexes match the `[N]` markers in `TutorAnswer.text`.

### Frontend tests

Add or update tests that prove:

- `splitIntoBlocks` preserves formal statement blockquotes and math boundaries,
- source rows are addressed by `id="cite-N"`,
- clicking a citation pill triggers the expected open-and-scroll behavior for valid indices.

### Browser verification

Use tutor mode on `:5175` with an answer containing formal statements and citations. Confirm:

- no raw `>` leakage,
- paragraph breaks look correct,
- equations render through KaTeX,
- inline `[N]` values match Sources entries,
- clicking pills opens Sources and scrolls to the right row.

## Risks

### Risk: parser changes affect older tutor answers

Mitigation: keep `splitIntoBlocks` changes narrowly structural and cover existing expected block types in tests.

### Risk: definition-recovery branch work already changed nearby behavior

Mitigation: prefer the smallest edits in `_render_formal_statements`, `_convert_to_tutor_answer`, and `TutorView`; do not refactor surrounding tutor assembly.

### Risk: array-order assumptions survive in unnoticed code paths

Mitigation: inspect and test both source-panel rendering and inline pill rendering against explicit `index` values.

## Definition Of Done

The work is done when:

- the three pending tutor issues are fixed together,
- backend and frontend tests covering them pass,
- browser verification on `:5175` confirms render, numbering, and linking behavior,
- any docs touched by the final implementation are updated on the required surfaces.
