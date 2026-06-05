# Pipeline Modal — Phase Colors + Auto-Fit Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Color-group every mode-modal pipeline node by functional phase (planning/retrieval/generation/vision/io) and make the tutor diagram's cards auto-fit their text instead of truncating.

**Architecture:** A single shared phase taxonomy (`pipelinePhases.ts`) drives `data-phase` attributes + CSS color tokens on all three diagram components. The tutor `PipelineDiagram` switches from fixed `ROW_DEF` heights to a measured reflow (refs + `useLayoutEffect`) with the old heights as jsdom/SSR fallbacks. The shared `FlowDiagram` (QA + chapter) just gains phase attrs.

**Tech Stack:** React 18 + TypeScript + Vite, vitest + `renderToStaticMarkup`, CSS custom properties.

**Spec:** `docs/superpowers/specs/2026-06-04-pipeline-modal-phase-colors-design.md`

All commands run from `web/` unless noted. Test runner: `npx vitest run <file>`.

---

## File Structure

- `web/src/data/pipelinePhases.ts` — `Phase` type, `PHASE_OF` (nodeId→phase), `PHASE_META` (chip label), `phaseOf(id)`. One responsibility: classify a node id into a phase. (new)
- `web/src/data/pipelinePhases.test.ts` — unit tests. (new)
- `web/src/styles/app.css` — `--phase-*` tokens (light+dark) + `[data-phase]` node styling + phase chip + remove tutor clamp/ellipsis. (modify)
- `web/src/components/FlowDiagram.tsx` — add `data-phase` + phase chip per node (covers QA + chapter). (modify)
- `web/src/components/PipelineDiagram.tsx` — measured reflow + `data-phase` + drop fixed node heights. (modify)
- Tests: `FlowDiagram.test.tsx`, `PipelineDiagram.test.tsx` (modify).
- Docs: `docs/services/chat-features/36-deep-tutor.md`, `docs/common ground/Elements/chat.html` (legend).

---

## Task 1: `pipelinePhases.ts` — shared taxonomy

**Files:**
- Create: `web/src/data/pipelinePhases.ts`
- Test: `web/src/data/pipelinePhases.test.ts`

- [ ] **Step 1: Write failing tests**

Create `web/src/data/pipelinePhases.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { phaseOf, PHASE_META, type Phase } from "./pipelinePhases";

describe("phaseOf", () => {
  it("maps tutor nodes to phases", () => {
    expect(phaseOf("input")).toBe("io");
    expect(phaseOf("output")).toBe("io");
    expect(phaseOf("expansion")).toBe("planning");
    expect(phaseOf("plan")).toBe("planning");
    expect(phaseOf("retrieval")).toBe("retrieval");
    expect(phaseOf("rerank")).toBe("retrieval");
    expect(phaseOf("diversity")).toBe("retrieval");
    expect(phaseOf("coverage")).toBe("retrieval");
    expect(phaseOf("drafting")).toBe("generation");
    expect(phaseOf("draft")).toBe("generation");
    expect(phaseOf("orchestrator")).toBe("generation");
    expect(phaseOf("worker1")).toBe("generation");
    expect(phaseOf("synthesizer")).toBe("generation");
    expect(phaseOf("image_judge")).toBe("vision");
    expect(phaseOf("formula_recovery")).toBe("vision");
    expect(phaseOf("vision_explain")).toBe("vision");
  });

  it("maps qa + chapter nodes to phases", () => {
    expect(phaseOf("scope")).toBe("planning");
    expect(phaseOf("clarify")).toBe("planning");
    expect(phaseOf("resolve")).toBe("planning");
    expect(phaseOf("parse")).toBe("planning");
    expect(phaseOf("map")).toBe("planning");
    expect(phaseOf("retrieve")).toBe("retrieval");
    expect(phaseOf("fetch")).toBe("retrieval");
    expect(phaseOf("generate")).toBe("generation");
    expect(phaseOf("teach")).toBe("generation");
    expect(phaseOf("stitch")).toBe("generation");
    expect(phaseOf("ground")).toBe("generation");
    expect(phaseOf("verify")).toBe("generation");
  });

  it("falls back to generation for unknown ids", () => {
    expect(phaseOf("totally-new-node")).toBe("generation");
  });

  it("has a chip label for every phase", () => {
    const phases: Phase[] = ["io", "planning", "retrieval", "generation", "vision"];
    for (const p of phases) expect(PHASE_META[p].label.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run, verify FAIL**

Run: `npx vitest run src/data/pipelinePhases.test.ts`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `web/src/data/pipelinePhases.ts`:
```ts
// Single source of truth: classify any pipeline node id (tutor / qa / chapter)
// into a functional phase, used for color-grouping in the mode-modal diagrams.

export type Phase = "io" | "planning" | "retrieval" | "generation" | "vision";

export interface PhaseMeta {
  label: string; // short chip text shown in the node header
}

export const PHASE_META: Record<Phase, PhaseMeta> = {
  io:         { label: "I/O" },
  planning:   { label: "PLAN" },
  retrieval:  { label: "RETRIEVAL" },
  generation: { label: "GENERATION" },
  vision:     { label: "VISION" },
};

// Explicit id → phase. Covers tutor (tutorPipeline.ts + orchestrator cluster),
// qa (qaPipeline.ts), and chapter (chapterPipeline.ts) node ids.
export const PHASE_OF: Record<string, Phase> = {
  // tutor — io
  input: "io", output: "io",
  // tutor — planning
  expansion: "planning", plan: "planning",
  // tutor — retrieval
  retrieval: "retrieval", rerank: "retrieval", diversity: "retrieval", coverage: "retrieval",
  // tutor — generation (incl. orchestrator cluster)
  drafting: "generation", draft: "generation", orchestrator: "generation",
  worker1: "generation", worker2: "generation", worker3: "generation", synthesizer: "generation",
  // tutor — vision
  image_judge: "vision", formula_recovery: "vision", vision_explain: "vision",
  // qa
  scope: "planning", retrieve: "retrieval", generate: "generation", verify: "generation",
  clarify: "planning",
  // chapter (facilitate / resume)
  parse: "planning", fetch: "retrieval", resolve: "planning", map: "planning",
  stitch: "generation", ground: "generation", teach: "generation",
};

export function phaseOf(id: string): Phase {
  return PHASE_OF[id] ?? "generation";
}
```

- [ ] **Step 4: Run, verify PASS**

Run: `npx vitest run src/data/pipelinePhases.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/data/pipelinePhases.ts web/src/data/pipelinePhases.test.ts
git commit -m "feat(modal): shared pipeline phase taxonomy (phaseOf + PHASE_META)"
```

---

## Task 2: CSS — phase tokens, node styling, de-clamp

**Files:**
- Modify: `web/src/styles/app.css`

No new test (pure CSS); verified visually in Task 5. Keep edits surgical.

- [ ] **Step 1: Add phase tokens (dark = default, light = override)**

Find the `:root` / dark token block and the light-theme block in `app.css` (search for `--accent-primary`). Add these tokens alongside the existing accent tokens.

In the DARK / default token scope add:
```css
  --phase-planning: #D98E04;
  --phase-retrieval: #4D6BFE;
  --phase-generation: var(--accent-primary, #E5484D);
  --phase-vision: #A371F7;
  --phase-io: var(--text-tertiary, #9aa1aa);
```
In the LIGHT-theme token scope (the selector that redefines `--accent-primary` to `#1E3A8A`) add:
```css
  --phase-planning: #B45309;
  --phase-retrieval: #3743C4;
  --phase-generation: var(--accent-primary, #1E3A8A);
  --phase-vision: #7C3AED;
  --phase-io: var(--text-tertiary);
```
(If you cannot locate a distinct light scope, place the light values under the existing light-theme selector used for `--accent-primary`. Do NOT introduce `rgba(63,169,255,*)` — forbidden by invariant 12.)

- [ ] **Step 2: Phase-driven node styling**

Replace the existing `.pipe2__node--llm` rule (currently `border-left: 3px solid var(--accent, #E5484D);`) with phase-driven styling. After the `.pipe2__node { ... }` base rule, add:
```css
/* phase color-grouping (shared by tutor PipelineDiagram + qa/chapter FlowDiagram) */
.pipe2__node[data-phase] {
  border-left: 3px solid var(--phase-generation);
  background: color-mix(in srgb, var(--phase-generation) 8%, var(--bg-secondary, #16161a));
}
.pipe2__node[data-phase="planning"]   { border-left-color: var(--phase-planning);   background: color-mix(in srgb, var(--phase-planning) 8%,   var(--bg-secondary, #16161a)); }
.pipe2__node[data-phase="retrieval"]  { border-left-color: var(--phase-retrieval);  background: color-mix(in srgb, var(--phase-retrieval) 8%,  var(--bg-secondary, #16161a)); }
.pipe2__node[data-phase="generation"] { border-left-color: var(--phase-generation); background: color-mix(in srgb, var(--phase-generation) 8%, var(--bg-secondary, #16161a)); }
.pipe2__node[data-phase="vision"]     { border-left-color: var(--phase-vision);     background: color-mix(in srgb, var(--phase-vision) 8%,     var(--bg-secondary, #16161a)); }
.pipe2__node--io[data-phase] { border-left: 1px dashed var(--phase-io); background: transparent; }

/* phase chip in the node header */
.pipe2__phase-chip {
  font-size: 0.55rem; text-transform: uppercase; letter-spacing: 0.06em;
  padding: 0 5px; border-radius: 7px; flex-shrink: 0;
  color: var(--phase-generation); border: 1px solid var(--phase-generation);
}
.pipe2__phase-chip[data-phase="planning"]   { color: var(--phase-planning);   border-color: var(--phase-planning); }
.pipe2__phase-chip[data-phase="retrieval"]  { color: var(--phase-retrieval);  border-color: var(--phase-retrieval); }
.pipe2__phase-chip[data-phase="generation"] { color: var(--phase-generation); border-color: var(--phase-generation); }
.pipe2__phase-chip[data-phase="vision"]     { color: var(--phase-vision);     border-color: var(--phase-vision); }
.pipe2__phase-chip[data-phase="io"]         { color: var(--phase-io);         border-color: var(--phase-io); }
```
Delete the now-redundant `.pipe2__node--llm { border-left: 3px solid var(--accent, #E5484D); }` line.

- [ ] **Step 3: De-clamp (auto-fit text)**

Change the description clamp so text is not truncated. Replace:
```css
.pipe2__node-desc--clamp {
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3;
  overflow: hidden;
}
```
with:
```css
/* auto-fit: descriptions wrap fully, no line clamp */
.pipe2__node-desc--clamp { overflow: visible; }
```
And change `.pipe2__model-fixed` so the model name wraps instead of ellipsis-truncating: in that rule replace
`white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%;`
with
`white-space: normal; overflow-wrap: anywhere; max-width: 100%;`

- [ ] **Step 4: Sanity check**

Run: `npx vitest run` (CSS has no tests; ensure nothing imports broke — full suite still green here, phase attrs not added yet so diagrams render unchanged colors via `[data-phase]` absent).
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/styles/app.css
git commit -m "style(modal): phase color tokens + data-phase node styling; de-clamp cards"
```

---

## Task 3: `FlowDiagram.tsx` — phase attrs (QA + chapter)

**Files:**
- Modify: `web/src/components/FlowDiagram.tsx`
- Test: `web/src/components/FlowDiagram.test.tsx`

- [ ] **Step 1: Write failing test**

First READ `web/src/components/FlowDiagram.test.tsx` to match its import + render style. Then add:
```tsx
it("tags each node with its phase (data-phase)", () => {
  const html = renderToStaticMarkup(
    <FlowDiagram
      nodes={[
        { id: "scope",    label: "Scope",    desc: "d", kind: "llm",  defaultModel: "m" },
        { id: "retrieve", label: "Retrieve", desc: "d", kind: "data", defaultModel: "" },
        { id: "generate", label: "Generate", desc: "d", kind: "llm",  defaultModel: "m" },
      ]}
      inputLabel="Question"
      outputLabel="Answer"
      providers={[]}
      stageModels={{}}
      onStageModelChange={() => {}}
    />,
  );
  expect(html).toContain('data-phase="planning"');   // scope
  expect(html).toContain('data-phase="retrieval"');  // retrieve
  expect(html).toContain('data-phase="generation"'); // generate
});
```
(If `FlowDiagram.test.tsx` lacks a `renderToStaticMarkup` import, add `import { renderToStaticMarkup } from "react-dom/server";` matching the pattern in `PipelineDiagram.test.tsx`.)

- [ ] **Step 2: Run, verify FAIL**

Run: `npx vitest run src/components/FlowDiagram.test.tsx`
Expected: FAIL (no `data-phase` yet).

- [ ] **Step 3: Implement**

In `web/src/components/FlowDiagram.tsx`:
1. Add import at top: `import { phaseOf, PHASE_META } from "../data/pipelinePhases";`
2. Find the per-node render (the `.map` that emits `<div className={"pipe2__node flow__node pipe2__node--" + n.kind}>`). Add `data-phase` + chip. Replace that opening div + its header so it reads:
```tsx
            <div
              className={"pipe2__node flow__node pipe2__node--" + n.kind}
              data-phase={phaseOf(n.id)}
            >
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
                <span className="pipe2__phase-chip" data-phase={phaseOf(n.id)}>
                  {PHASE_META[phaseOf(n.id)].label}
                </span>
              </div>
```
(Keep the rest of the node body — desc + model control — unchanged. If the existing header already renders a label/badge, preserve the model badge logic below the header; only ADD the phase chip and the two `data-phase` attrs. Read the current JSX and merge carefully.)
3. The two `io` endpoint divs (`pipe2__node--io flow__node` for input/output): add `data-phase="io"` to each.

- [ ] **Step 4: Run, verify PASS + no regressions**

Run: `npx vitest run src/components/FlowDiagram.test.tsx src/components/QAPipelineDiagram.test.tsx src/components/ChapterPipelineDiagram.test.tsx`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/FlowDiagram.tsx web/src/components/FlowDiagram.test.tsx
git commit -m "feat(modal): phase color attrs + chip on FlowDiagram (qa/chapter)"
```

---

## Task 4: `PipelineDiagram.tsx` — measured auto-fit + phase attrs

**Files:**
- Modify: `web/src/components/PipelineDiagram.tsx`
- Test: `web/src/components/PipelineDiagram.test.tsx`

This is the layout-engine change. Read the whole current file first.

- [ ] **Step 1: Write failing tests**

Add to `web/src/components/PipelineDiagram.test.tsx`:
```tsx
it("tags nodes with their phase (single layout)", () => {
  const html = renderToStaticMarkup(
    <PipelineDiagram
      pickerModel="gpt-4o" stageModels={{}} providers={PROVIDERS}
      onStageModelChange={() => {}} diversityAuthors={3} onDiversityChange={() => {}}
      tutorWorkflow="single" onWorkflowChange={() => {}}
    />,
  );
  expect(html).toContain('data-phase="planning"');   // query planner / planner
  expect(html).toContain('data-phase="retrieval"');  // retrieval/rerank/diversity/coverage
  expect(html).toContain('data-phase="vision"');     // figure judge / vision explain
  expect(html).toContain('data-phase="generation"'); // drafting / draft
});

it("formula_recovery node carries the vision phase (orchestrator layout)", () => {
  const html = renderToStaticMarkup(
    <PipelineDiagram
      pickerModel="gpt-4o" stageModels={{}} providers={PROVIDERS}
      onStageModelChange={() => {}} diversityAuthors={3} onDiversityChange={() => {}}
      tutorWorkflow="orchestrator" onWorkflowChange={() => {}}
    />,
  );
  // formula_recovery present and tagged vision; orchestrator/workers/synth = generation
  expect(html).toMatch(/data-node="formula_recovery"[^>]*data-phase="vision"|data-phase="vision"[^>]*data-node="formula_recovery"/);
});
```
(If `data-node` and `data-phase` order makes the regex brittle, instead assert both substrings exist: `expect(html).toContain('data-node="formula_recovery"')` and `expect(html).toContain('data-phase="vision"')`. Use whichever is robust against attribute order.)

- [ ] **Step 2: Run, verify FAIL**

Run: `npx vitest run src/components/PipelineDiagram.test.tsx`
Expected: FAIL (no `data-phase` yet).

- [ ] **Step 3: Convert fixed layout to measured builders**

In `PipelineDiagram.tsx`:

(a) Update the React import to include hooks:
```tsx
import { useLayoutEffect, useRef, useState } from "react";
```
(b) Add the phase import:
```tsx
import { phaseOf, PHASE_META } from "../data/pipelinePhases";
```
(c) Build a default-height map from `ROW_DEF` + cluster nodes. After the `ROW_DEF` definition add:
```tsx
const DEFAULT_H: Record<string, number> = {
  ...Object.fromEntries(ROW_DEF.map((r) => [r.id, r.h])),
  orchestrator: 104, worker1: 56, worker2: 56, worker3: 56,
  formula_recovery: 88, synthesizer: 66,
};
```
(d) Replace the module-level `BASE_LAYOUT` / `BASE_H` constants AND the `ORC_*` geometry constants + `buildOrchLayout` with height-parametrized builder functions. Delete `BASE_LAYOUT`, `BASE_H`, `ORCH_Y`, `ORCH_H`, `WORKER_ROW_Y`, `WORKER_H`, `FR_Y`, `FR_H`, `SYNTH_Y`, `SYNTH_H`, `TAIL_SHIFT`, `ORC_LAYOUT`, `ORCH_LAYOUT_FULL`, `ORCH_CANVAS_H`, and the old `buildOrchLayout`. KEEP `WORKER_W`, `WORKER_GAP`, `WORKERS_TOTAL_W`, `WORKERS_LEFT_X` (recompute `WORKERS_LEFT_X` inline if it referenced `BASE_LAYOUT.draft`). Add:
```tsx
function buildBaseLayout(h: (id: string) => number): { layout: Record<string, Box>; height: number } {
  const layout: Record<string, Box> = {};
  let y = TOP;
  for (const r of ROW_DEF) {
    const hh = h(r.id);
    layout[r.id] = r.io ? { x: IO_X, y, w: IO_W, h: hh } : { x: CX, y, w: CW, h: hh };
    y += hh + GAP;
  }
  return { layout, height: y + 8 };
}

const PRE_CLUSTER_IDS = [
  "input", "expansion", "retrieval", "rerank", "diversity",
  "coverage", "image_judge", "plan", "drafting",
] as const;
const WORKERS_LEFT_X = CX + (CW - WORKERS_TOTAL_W) / 2;

function buildOrchLayout(h: (id: string) => number): { layout: Record<string, Box>; height: number } {
  const layout: Record<string, Box> = {};
  let y = TOP;
  for (const id of PRE_CLUSTER_IDS) {
    const r = ROW_DEF.find((rr) => rr.id === id)!;
    const hh = h(id);
    layout[id] = r.io ? { x: IO_X, y, w: IO_W, h: hh } : { x: CX, y, w: CW, h: hh };
    y += hh + GAP;
  }
  const oH = h("orchestrator");
  layout.orchestrator = { x: CX, y, w: CW, h: oH };
  y += oH + GAP;
  const wH = Math.max(h("worker1"), h("worker2"), h("worker3"));
  layout.worker1 = { x: WORKERS_LEFT_X, y, w: WORKER_W, h: wH };
  layout.worker2 = { x: WORKERS_LEFT_X + WORKER_W + WORKER_GAP, y, w: WORKER_W, h: wH };
  layout.worker3 = { x: WORKERS_LEFT_X + 2 * (WORKER_W + WORKER_GAP), y, w: WORKER_W, h: wH };
  y += wH + GAP;
  const frH = h("formula_recovery");
  layout.formula_recovery = { x: CX, y, w: CW, h: frH };
  y += frH + GAP;
  const sH = h("synthesizer");
  layout.synthesizer = { x: CX, y, w: CW, h: sH };
  y += sH + GAP;
  for (const id of ["vision_explain", "output"] as const) {
    const r = ROW_DEF.find((rr) => rr.id === id)!;
    const hh = h(id);
    layout[id] = r.io ? { x: IO_X, y, w: IO_W, h: hh } : { x: CX, y, w: CW, h: hh };
    y += hh + GAP;
  }
  return { layout, height: y + 8 };
}
```
(Keep `WORKER_W = 68`, `WORKER_GAP = 6`, `WORKERS_TOTAL_W = 3 * WORKER_W + 2 * WORKER_GAP` as-is.)

- [ ] **Step 4: Wire measurement into the component**

Inside `PipelineDiagram(...)`, replace the `if (!isOrchLayout) { effectiveNodes = ...; effectiveLayout = BASE_LAYOUT; canvasH = BASE_H } else { ... }` block with measured builders. Add near the top of the component body (after `isOrchLayout`):
```tsx
  const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [measured, setMeasured] = useState<Record<string, number>>({});
  const h = (id: string) => measured[id] || DEFAULT_H[id] || 100;
```
Keep the `effectiveNodes` / `effectiveEdges` derivation exactly as it is (the node/edge sets are unchanged). Replace ONLY the layout + canvas derivation:
```tsx
  const built = isOrchLayout ? buildOrchLayout(h) : buildBaseLayout(h);
  const effectiveLayout = built.layout;
  const canvasH = built.height;
```
Then add the measuring effect (place it right after the derivations, before `edgePath`):
```tsx
  useLayoutEffect(() => {
    const next: Record<string, number> = {};
    for (const id of Object.keys(nodeRefs.current)) {
      const el = nodeRefs.current[id];
      if (el && el.offsetHeight > 0) next[id] = el.offsetHeight;
    }
    const keys = new Set([...Object.keys(next), ...Object.keys(measured)]);
    let changed = false;
    for (const k of keys) if (next[k] !== measured[k]) { changed = true; break; }
    if (changed) setMeasured(next);
  });
```

- [ ] **Step 5: Add ref + data-phase to every node div; drop fixed height**

For EACH node-rendering `<div className="pipe2__node...">` in the component (the diversity, drafting, plan, orchestrator, worker, synthesizer, and the generic "all other nodes" branches):
1. Add a ref callback: `ref={(el) => { nodeRefs.current[n.id] = el; }}`.
2. Add `data-phase={phaseOf(n.id)}`.
3. In its inline `style`, REMOVE `height: box.h` (keep `left: box.x, top: box.y, width: box.w`; keep `position: "absolute"`). Heights now come from content.
4. Add a phase chip in the node header `pipe2__node-hd` (next to the existing label/badge), EXCEPT for worker nodes (too small) and io nodes:
```tsx
                <span className="pipe2__phase-chip" data-phase={phaseOf(n.id)}>
                  {PHASE_META[phaseOf(n.id)].label}
                </span>
```
For the worker branch: add the ref + `data-phase` + drop height, but NO chip (keep it minimal). For the generic branch's io nodes (`n.kind === "io"`): add ref + `data-phase` + drop height, but NO chip.

Note: the generic branch currently sets `height: box.h` in the style object and renders the header; add the chip inside its `pipe2__node-hd` after the label, but only when `n.kind !== "io"`.

- [ ] **Step 6: Run, verify PASS + no regressions**

Run: `npx vitest run src/components/PipelineDiagram.test.tsx`
Expected: all pass (the 30 existing + 2 new). The existing geometry/orchestrator tests still pass because jsdom `offsetHeight` is 0 → `h()` falls back to `DEFAULT_H`, reproducing the old fixed heights; `data-node`/label assertions are markup-based.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/PipelineDiagram.tsx web/src/components/PipelineDiagram.test.tsx
git commit -m "feat(modal): measured auto-fit layout + phase color attrs in tutor PipelineDiagram"
```

---

## Task 5: Docs lockstep + full suite + browser verify

**Files:**
- Modify: `docs/services/chat-features/36-deep-tutor.md`, `docs/common ground/Elements/chat.html`

- [ ] **Step 1: Full frontend suite**

Run (from `web/`): `npx vitest run`
Expected: all pass. Fix any regression before proceeding.

- [ ] **Step 2: Docs — phase legend**

(a) `docs/services/chat-features/36-deep-tutor.md`: under the mermaid graph, add a one-line legend:
`> Modal phase colors: Planning (amber) · Retrieval (indigo) · Generation (red) · Vision (violet) · I/O (grey).`

(b) `docs/common ground/Elements/chat.html`: in the Deep-tutor pipeline `<section id="pipeline">`, add a small legend line (plain HTML, match surrounding style) listing the five phase→color pairs so the reference doc matches the modal.

- [ ] **Step 3: Commit docs**

```bash
git add "docs/services/chat-features/36-deep-tutor.md" "docs/common ground/Elements/chat.html"
git commit -m "docs(modal): phase color legend (tutor graph + Elements reference)"
```

- [ ] **Step 4: Browser verify (live, :5175)**

With dev running (`./scripts/dev.sh`), the controller (not a subagent) will:
- Open the Tutor (i) modal: confirm phase colors + chips on each node; switch Drafting workflow → Orchestrator and Deep synthesis; confirm the cluster (orchestrator/workers/formula_recovery/synthesizer) is `generation`/`vision` colored and that cards auto-fit (no truncated descriptions or model names) in both layouts.
- Open Q&A, Facilitate, Resume (i) modals: confirm nodes are phase-colored with chips.
- Screenshot each. (No commit — verification.)

---

## Self-Review

- **Spec coverage:** taxonomy → Task 1; CSS tokens + de-clamp → Task 2; QA/chapter (FlowDiagram) phase → Task 3; tutor measured auto-fit + phase → Task 4; docs legend + browser verify → Task 5. All spec sections covered.
- **Placeholders:** none — every step has concrete code/commands. The only read-and-adapt notes (locate light-theme token scope in app.css; merge phase chip into existing FlowDiagram/PipelineDiagram header JSX) are explicit about what to preserve.
- **Type/name consistency:** `Phase`, `phaseOf`, `PHASE_META`, `PHASE_OF` used identically across Tasks 1/3/4. `buildBaseLayout`/`buildOrchLayout` return `{ layout, height }` and are consumed as `built.layout`/`built.height`. `DEFAULT_H` keys cover every id referenced by both builders (ROW_DEF ids + orchestrator/worker1-3/formula_recovery/synthesizer). `h(id)` fallback chain (`measured → DEFAULT_H → 100`) guarantees a height for every node. jsdom `offsetHeight===0` path preserves the legacy fixed geometry so existing tests hold.
