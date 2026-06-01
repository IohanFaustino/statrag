# Non-tutor mode modals — pipeline + provider switch

**Date:** 2026-06-01
**Status:** Approved (design)
**Scope:** Frontend (web/) only, plus provider-icon additions. No backend changes.

## Problem

Each chat mode has an info `(i)` modal that should show its pipeline structure and
let the user swap the model/provider per stage. Today only **tutor** has this
(rich `AboutModelModal` + `PipelineDiagram` with per-node `NodeModelDropdown`).

- **Q&A** modal (`QAModeModal` + `QAPipeline`) is **read-only** — shows the
  pipeline as a static list with no provider switch.
- **facilitate** / **resume** (chapter modes) have **no modal at all** and no
  `(i)` button in `ModePicker`, even though `chapterPipeline.ts` data exists.

The backend already accepts per-stage overrides via `ChatRequest.stageModels`
for both Q&A (`_model_for` over scope/generate/verify) and chapter
(`_model_for` over parse/resolve/map/stitch/ground). **The gap is purely
frontend.**

Extra task: the provider icons only cover openai/deepseek/groq. Add **gemini**
(provider id `google`) and **alibaba** (provider id `alibaba`, Qwen models).

## Decisions (from brainstorming)

1. **Per-mode diagram components** — build `QAPipelineDiagram` +
   `ChapterPipelineDiagram` alongside the existing tutor `PipelineDiagram`.
   Tutor code is untouched (no shared-component refactor).
2. **Per-node dropdowns** — each LLM node gets a `NodeModelDropdown` that writes
   `stageModels[node.id]`, matching tutor and the backend's per-stage keys.
3. **Two separate chapter modals** — `ChapterFacilitateModal` +
   `ChapterResumeModal`, each rendering the shared `ChapterPipelineDiagram` with
   its `mode` prop.

## Key invariant that makes this clean

Stage keys are **disjoint** across modes:
- tutor: expansion, draft, plan, critique, image_judge, …
- qa: scope, generate, verify
- chapter: parse, resolve, map, stitch, ground

And in both `qaPipeline.ts` and `chapterPipeline.ts`, **node id == stage key**.
So a single persisted `stageModels` dict (already in `App.tsx`,
`"statrag.stageModels"`) holds all modes' overrides without collision. Each
backend `_model_for(stage, req)` reads only its own keys; extra keys are
ignored. **No new App state for overrides** — only modal open flags.

## Components

### New — diagram components

**`web/src/components/QAPipelineDiagram.tsx`**
- Renders `QA_PIPELINE.nodes` in the existing vertical-list layout (the
  `qa-pipeline` CSS), not tutor's absolute SVG canvas (lighter, less drift).
- For `kind === "llm"` nodes (scope, generate, verify): render
  `NodeModelDropdown` with `value = stageModels[node.id] ?? node.defaultModel`,
  `onChange={(id) => onStageModelChange(node.id, id)}`.
- For `kind === "data"` nodes (retrieve): render a fixed label
  (`node.defaultModel`), no dropdown.
- Props: `{ providers, stageModels, onStageModelChange }`.

**`web/src/components/ChapterPipelineDiagram.tsx`**
- Same pattern over `CHAPTER_PIPELINE.nodes`. LLM nodes parse/resolve/map/
  stitch/ground get dropdowns; data node fetch is a fixed label.
- Extra prop `mode: "facilitate" | "resume"` — used only to tweak the map-node
  sublabel copy (facilitate = "teach each section"; resume = "compress each
  section"). Diagram shape identical for both.
- Props: `{ mode, providers, stageModels, onStageModelChange }`.

### Remade — modals (mirror `AboutModelModal` draft/commit pattern)

Each modal: `FocusModal` shell → header (title + blurb + close) → diagram →
footer with **Cancel / Apply** and an "Unsaved / No changes" hint. Edits go to a
local `draftStageModels`, re-seeded from the applied `stageModels` on open;
**Apply** calls `onApply({ stageModels: draft })`, **Cancel** discards.

- **`web/src/components/modals/QAModeModal.tsx`** — remade from read-only.
  Replaces `<QAPipeline />` with `<QAPipelineDiagram …>` + footer. Keeps the
  Q&A title/blurb.
- **`web/src/components/modals/ChapterFacilitateModal.tsx`** — renders
  `<ChapterPipelineDiagram mode="facilitate" …>`. Title "Facilitate mode",
  blurb describing the ordered didactic walkthrough.
- **`web/src/components/modals/ChapterResumeModal.tsx`** — renders
  `<ChapterPipelineDiagram mode="resume" …>`. Title "Resume mode", blurb
  describing the ordered compressed recap.

The existing read-only `QAPipeline.tsx` is removed (or left unused and deleted)
once `QAPipelineDiagram` replaces it.

### App.tsx wiring

- Add open flags: `facilitateModalOpen`, `resumeModalOpen` (qa flag exists as
  `qaModalOpen`).
- Pass new handlers to `ModePicker`: `onModeAboutFacilitate`,
  `onModeAboutResume`.
- Render `ChapterFacilitateModal` + `ChapterResumeModal` next to the others,
  wired to `providers`, `stageModels`, and an `onApply` that merges the draft
  into the persisted `stageModels` (`setStageModels((prev) => ({ ...prev,
  ...cfg.stageModels }))`).
- `QAModeModal` gains the same `providers` / `stageModels` / `onApply` props.

### ModePicker.tsx

- Add props `onAboutFacilitate?` / `onAboutResume?`.
- Currently only tutor + qa cards render the `(i)` button. Add the same
  info-circle `(i)` button to the **facilitate** and **resume** cards, opening
  their modals. Reuse the existing info-circle SVG markup.

### Provider SVGs (extra task)

- Extend frontend type: `web/src/types.ts`
  `ProviderId = "openai" | "deepseek" | "groq" | "google" | "alibaba"`.
- Add `id === "google"` (Gemini — Google four-color spark/star mark) and
  `id === "alibaba"` (Qwen / Alibaba mark) branches to the **three** duplicated
  `ProviderIcon` functions:
  - `web/src/components/ModelPicker.tsx`
  - `web/src/components/NodeModelDropdown.tsx`
  - `web/src/components/Topbar.tsx`
- Icons are inline SVG in the same visual language as the existing marks
  (24×24 viewBox, `currentColor` where the others use it; Gemini may use its
  brand gradient/fill like the others use literal fills).

## Data flow

```
ModePicker (i) click → App opens <Mode>Modal
  → modal seeds draftStageModels from applied stageModels
  → user picks model per LLM node (NodeModelDropdown → draft[stage]=id)
  → Apply → App merges draft into persisted stageModels
  → useChat sends ChatRequest.stageModels with the active mode
  → backend _model_for(stage, req) reads its own stage keys
```

## Error handling / edge cases

- Unknown model id in `stageModels` → backend already falls back to the stage
  default (env or nano). Frontend dropdown only offers ids from `providers`.
- `providers` empty / `/api/models` failed → dropdowns show the node default
  label; switching is a no-op until providers load (same as tutor today).
- Sending tutor/other-mode keys in a Q&A request is harmless (disjoint keys).

## Testing

- **`QAPipelineDiagram.test.tsx`** — llm nodes render a dropdown; data node
  renders a fixed label; `onStageModelChange` fires with `(stageId, modelId)`;
  value reflects `stageModels[stage]` override.
- **`ChapterPipelineDiagram.test.tsx`** — same assertions over chapter nodes;
  map-node sublabel differs by `mode` prop.
- Existing `qaPipeline.test.ts` / `chapterPipeline.test.ts` (data shape) stay
  green. Tutor `PipelineDiagram.test.tsx` unaffected.
- `npm run build` + `vitest` green; browser check on :5175 that each mode's
  `(i)` opens an editable modal and Apply persists.

## Docs (interconnected-artifact rule)

- `docs/services/chat-features/51-qa-mode.md` — note the modal is now editable
  with per-stage provider switch.
- Chapter-modes feature doc (facilitate/resume) — same note + new modal cards.
- `docs/system/changelog.md` — entry.
- `docs/system/invariants.md` — if a relevant invariant exists about modal/
  pipeline parity, extend it; else skip.
- `docs/common ground/index.html` reference graph — update only if it depicts
  these modes' modals.

## Out of scope

- No backend changes (overrides already supported).
- No shared-diagram refactor of tutor's `PipelineDiagram`.
- No new env flags, no schema changes.
- No diversity/workflow controls for qa/chapter (tutor-only concepts).

## Files touched

New:
- `web/src/components/QAPipelineDiagram.tsx`
- `web/src/components/ChapterPipelineDiagram.tsx`
- `web/src/components/modals/ChapterFacilitateModal.tsx`
- `web/src/components/modals/ChapterResumeModal.tsx`
- `web/src/components/QAPipelineDiagram.test.tsx`
- `web/src/components/ChapterPipelineDiagram.test.tsx`

Edited:
- `web/src/components/modals/QAModeModal.tsx`
- `web/src/components/ModePicker.tsx`
- `web/src/components/ModelPicker.tsx`
- `web/src/components/NodeModelDropdown.tsx`
- `web/src/components/Topbar.tsx`
- `web/src/types.ts`
- `web/src/App.tsx`

Removed:
- `web/src/components/QAPipeline.tsx` (replaced by `QAPipelineDiagram`)
