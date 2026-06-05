# Pipeline Modal — Phase Colors + Auto-Fit Cards (design)

**Date:** 2026-06-04
**Status:** approved (design), pending implementation
**Scope:** frontend-only (React/Vite/TS) — the mode (i) modals' pipeline graphs. No backend/pipeline-logic change.

## Problem

The deep-tutor pipeline modal (`PipelineDiagram`) reads as an undifferentiated chain:

- **No functional grouping.** Only two visual variants exist — `io` (dashed) and everything else (dark card); `llm` nodes get a thin red left stripe. Retrieval, planning, generation, and vision stages all look identical, so the graph does not convey distinct pipeline phases or the deep-agent step separation.
- **Fixed card sizes truncate text.** Node heights are hand-set in `ROW_DEF` with `-webkit-line-clamp: 3` on descriptions and `text-overflow: ellipsis` on model names → descriptions clip and model labels cut off (e.g. "gpt-4o vision + formula ca…").

## Goals

1. **Color-group nodes by pipeline phase** across all mode modals (Tutor, Q&A, Facilitate, Resume), from a single shared taxonomy.
2. **Auto-fit card height to content** in the tutor diagram — no truncation; cards grow/shrink to their text.
3. Keep all existing behavior: model dropdowns, workflow/diversity selectors, orchestrator cluster, loop-back edge, single-vs-orchestrator layouts.

## Non-goals

- No change to pipeline logic, prompts, schemas, or SSE.
- No new diagram features (zoom, pan, collapse).
- No restyle of unrelated modal chrome.

## Phase taxonomy (single source of truth)

New module `web/src/data/pipelinePhases.ts`:

```ts
export type Phase = "io" | "planning" | "retrieval" | "generation" | "vision";

// nodeId → phase, covering tutor + qa + chapter node ids.
export const PHASE_OF: Record<string, Phase> = { /* see table */ };

export interface PhaseMeta { label: string; }   // short chip label, e.g. "RETRIEVAL"
export const PHASE_META: Record<Phase, PhaseMeta>;

export function phaseOf(id: string): Phase;      // PHASE_OF[id] ?? "generation" fallback
```

Mapping (tutor node ids shown; QA/chapter ids mapped by the same rules):

| Phase | CSS token | Tutor nodes | QA / Chapter nodes (by rule) |
|---|---|---|---|
| `io` | neutral grey, dashed | `input`, `output` | question/answer endpoints |
| `planning` | amber | `expansion` (query planner), `plan` (planner) | scope-resolve, plan/clarify |
| `retrieval` | indigo | `retrieval`, `rerank`, `diversity`, `coverage` | retrieve / fetch-chapter |
| `generation` | red accent | `drafting`, `draft`, `orchestrator`, `worker1/2/3`, `synthesizer` | generate / teach / stitch / verify |
| `vision` | violet | `image_judge`, `formula_recovery`, `vision_explain` | (none today) |

The actual QA/chapter node ids will be read from `qaPipeline.ts` / `chapterPipeline.ts` during implementation and added to `PHASE_OF` explicitly (no guessing).

### Colors (CSS tokens in `app.css`, light + dark)

| Token | Dark | Light |
|---|---|---|
| `--phase-planning` | `#D98E04` | `#B45309` |
| `--phase-retrieval` | `#4D6BFE` | `#3743C4` |
| `--phase-generation` | `var(--accent-primary)` (`#E5484D` dark / `#1E3A8A` light) | same |
| `--phase-vision` | `#A371F7` | `#7C3AED` |
| `--phase-io` | `var(--text-tertiary)` | same |

Constraint: must NOT use `rgba(63,169,255,X)` (invariant 12 — electric blue is forbidden). Indigo `#4D6BFE` is allowed and already appears in the WF mermaid style.

### Node styling

Each node card:
- `border-left: 3px solid var(--phase-<p>)`.
- faint tinted background: `color-mix(in srgb, var(--phase-<p>) 8%, var(--bg-secondary))`.
- a phase chip in the header (`PHASE_META[p].label`, e.g. `RETRIEVAL`) in the phase color.
- locked nodes: unchanged `--locked` opacity (dimmer same hue).
- `data-phase="<p>"` attribute for testing.

## Auto-fit layout (tutor `PipelineDiagram.tsx`)

Replace fixed `ROW_DEF` heights with **measured reflow**:

1. Keep absolute positioning + the SVG edge layer (preserves curved edges, worker fan-out, loop-back arc).
2. Render nodes at their fixed `x`/width with auto height; attach a `ref` per node.
3. `useLayoutEffect`: read each `ref.offsetHeight`; build the row order (most rows = 1 node; the worker row = 3 nodes, row height = max of the three); compute cumulative `y` with the existing `GAP`; derive cluster geometry (orchestrator → worker row → formula_recovery → synthesizer) the same way but from measured heights; set `{ layout, canvasH }` into state; recompute edge paths from the new boxes.
4. Remove `-webkit-line-clamp` and the model-name `ellipsis` so content drives height.

**jsdom / SSR safety:** `offsetHeight` is `0` under `renderToStaticMarkup` / jsdom. Keep the current `ROW_DEF` numbers as **fallback defaults**: when a measured height is `0`/missing, use the default. So tests render every node with sensible heights; measured values override only in the live browser. This keeps all existing `renderToStaticMarkup` assertions working.

## Q&A + Chapter diagrams (`FlowDiagram.tsx`)

QA (`QAPipelineDiagram`) and Facilitate/Resume (`ChapterPipelineDiagram`) both render through the shared **`FlowDiagram.tsx`** (a flexbox vertical flow — already content-flexible). Change there once:
- apply `data-phase` + phase border/tint/chip via `phaseOf(node.id)`.
- drop any description clamp so text isn't truncated.

No layout-engine change needed for these (flexbox auto-sizes).

## Error handling / degradation

- `phaseOf` returns a `generation` fallback for unmapped ids → a new node never crashes the render; it just gets the default hue.
- Measured-layout effect guards against `0` heights (fallback) and runs on `[tutorWorkflow, diversityAuthors, providers]` changes so the layout re-measures when the cluster toggles.

## Testing

- `pipelinePhases.test.ts`: `phaseOf` returns the right phase for representative tutor/qa/chapter ids + fallback.
- `PipelineDiagram.test.tsx`: every rendered node carries the correct `data-phase`; `formula_recovery` → `vision`; orchestrator cluster nodes → `generation`; retrieval group → `retrieval`. (jsdom-safe; assertions are on markup, not measured geometry.)
- `FlowDiagram.test.tsx` (+ QA/Chapter diagram tests): nodes carry `data-phase`; no clamp class present.
- Manual: browser-verify on :5175 — open all four mode (i) modals, confirm phase colors + chips, and that the tutor cards auto-fit (no truncation) in both single-draft and orchestrator layouts. Screenshots.

## Lockstep (docs)

Presentation-only, but for graph fidelity:
- `docs/services/chat-features/36-deep-tutor.md`: add a one-line phase-color legend.
- `docs/common ground/Elements/chat.html`: add a small legend mapping phase → color so the reference graph matches the modal.

## Files

- New: `web/src/data/pipelinePhases.ts`, `web/src/data/pipelinePhases.test.ts`
- Modify: `web/src/components/PipelineDiagram.tsx` (measured reflow + phase render), `web/src/components/FlowDiagram.tsx` (phase render + de-clamp), `web/src/styles/app.css` (`--phase-*` tokens + node styling, remove clamp/ellipsis)
- Tests: `PipelineDiagram.test.tsx`, `FlowDiagram.test.tsx`, QA/Chapter diagram tests as needed
- Docs: `36-deep-tutor.md`, `Elements/chat.html`
