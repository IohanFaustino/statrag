# Tutor Modal Cosmetic Parity Implementation Plan

> Frontend only, `web/`. Make the tutor `PipelineDiagram` boxes read like the qa/chapter `FlowDiagram` boxes — a **description line inside each node** — while KEEPING the graph structure (loop-back arc, orchestrator branch, locked + SET choice nodes, SVG edges).

**Goal:** Add an in-box clamped description line under each tutor node's label (matching the other modals) and re-flow the absolute layout so boxes don't overlap. No structural/feature change to the graph.

**Architecture:** `PipelineDiagram.tsx` uses a hand-laid absolute px layout (`BASE_LAYOUT`) with fixed node heights; the orchestrator cluster + loop-back arc derive their geometry from those boxes. Refactor `BASE_LAYOUT` to be **computed cumulatively from an ordered list of per-node heights** so growing a node auto-reflows everything below it (and the orchestrator/loop geometry, which reads `BASE_LAYOUT.draft`, follows). Add a 3-line-clamped `.pipe2__node-desc` to each non-io, non-worker node. Reuse the `.pipe2__node-desc` class added earlier; add a `--clamp` modifier.

---

## Context

- File: `web/src/components/PipelineDiagram.tsx` (~512 lines). Read it fully before editing.
- `web/src/data/tutorPipeline.ts` — `TUTOR_PIPELINE.nodes` each have `desc` (long, 1–3 sentences). io nodes: `input`, `output`. data: retrieval, rerank, diversity, coverage, drafting. llm: expansion, image_judge, plan, draft, vision_explain.
- The other modals render desc via `web/src/components/FlowDiagram.tsx` (`pipe2__node-desc`). CSS `.pipe2__node-desc` already exists in `web/src/styles/app.css` (added with FlowDiagram).
- Orchestrator geometry (`ORCH_Y`, `WORKER_ROW_Y`, `SYNTH_Y`, `TAIL_SHIFT`, `ORC_LAYOUT`) reads from `BASE_LAYOUT.draft` — keep those references; they auto-adjust once `BASE_LAYOUT` is computed.
- Default workflow is "single" (linear chain + coverage→retrieval loop-back). Orchestrator cluster only renders when `tutorWorkflow === "orchestrator"`.
- Tests: `cd web && npx vitest run src/components/PipelineDiagram.test.tsx`. Type-check: `npx tsc --noEmit`. Build: `npm run build`.
- git hygiene: branch shared with a concurrent docs session. `git add` ONLY explicit paths. NEVER `git add -A`/`.`/`commit -a`.

---

## Task 1: Computed layout + in-box descriptions

**Files:** Modify `web/src/components/PipelineDiagram.tsx`, `web/src/styles/app.css`, `web/src/components/PipelineDiagram.test.tsx`.

- [ ] **Step 1: Replace the literal `BASE_LAYOUT` with a computed one.**

Find the current block (around lines 40–65: `const W = 520; const BASE_H = 1200; ... const BASE_LAYOUT: Record<string, Box> = { input: {...}, ... output: {...} };`). Replace the `BASE_H` constant and the literal `BASE_LAYOUT` with a generated layout, keeping `W`, `Box`, `GAP`, `CX`, `CW`:

```ts
const W = 520;
interface Box { x: number; y: number; w: number; h: number; }

// Vertical gap between rows.
const GAP = 18;
// Centred nodes geometry.
const CX = 144;   // left edge of centred nodes
const CW = 232;   // width of centred nodes
// io nodes are a touch narrower + centred in the 520 canvas.
const IO_X = 160;
const IO_W = 200;
const TOP = 8;    // top padding

// Ordered rows with per-node heights (sized to fit label + clamped desc +
// the model control). Growing a height auto-reflows everything below.
const ROW_DEF: ReadonlyArray<{ id: string; h: number; io?: boolean }> = [
  { id: "input",          h: 46,  io: true },
  { id: "expansion",      h: 122 },
  { id: "retrieval",      h: 104 },
  { id: "rerank",         h: 112 },
  { id: "diversity",      h: 116 },
  { id: "coverage",       h: 112 },
  { id: "image_judge",    h: 104 },
  { id: "plan",           h: 132 },
  { id: "drafting",       h: 132 },
  { id: "draft",          h: 104 },
  { id: "vision_explain", h: 112 },
  { id: "output",         h: 46,  io: true },
];

const BASE_LAYOUT: Record<string, Box> = (() => {
  const out: Record<string, Box> = {};
  let y = TOP;
  for (const r of ROW_DEF) {
    out[r.id] = r.io
      ? { x: IO_X, y, w: IO_W, h: r.h }
      : { x: CX,   y, w: CW,   h: r.h };
    y += r.h + GAP;
  }
  return out;
})();

const BASE_H = (() => {
  let y = TOP;
  for (const r of ROW_DEF) y += r.h + GAP;
  return y + 8; // bottom padding
})();
```

Remove the now-obsolete standalone `void GAP;` line if present (GAP is now used).

- [ ] **Step 2: Add a clamped description line to each node's render.**

In the render, add a description element to the nodes. Reuse `n.desc`. Apply to: the **generic node branch** (the catch-all `return` near the end), the **`plan`** branch, the **`diversity`** branch, the **`drafting`** branch, and the **`orchestrator`** branch. Do NOT add to io nodes, worker nodes, or synthesizer.

For each of those branches, immediately AFTER the closing `</div>` of `pipe2__node-hd` and BEFORE the model control / dropdown, insert:

```tsx
              <div className="pipe2__node-desc pipe2__node-desc--clamp" title={n.desc}>{n.desc}</div>
```

In the generic branch the node renders `n.kind !== "io"` controls; gate the desc the same way so io nodes stay terse:

```tsx
            {n.kind !== "io" && (
              <div className="pipe2__node-desc pipe2__node-desc--clamp" title={n.desc}>{n.desc}</div>
            )}
```

(The `plan` branch currently also renders a `pipe2__node-sublabel` "skipped when simple…" — keep it; place the desc line below the sublabel.)

- [ ] **Step 3: Add the clamp CSS.**

Append to `web/src/styles/app.css` right after the existing `.pipe2__node-desc { … }` rule:

```css
.pipe2__node-desc--clamp {
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3;
  overflow: hidden;
}
```

- [ ] **Step 4: Update the test** — add a desc assertion to `web/src/components/PipelineDiagram.test.tsx`. In the first `it(...)` (the single-workflow render), after the existing expects, add:

```tsx
    // nodes now show an in-box description line (parity with qa/chapter modals)
    expect(html).toContain("pipe2__node-desc");
    expect(html).toContain("Interprets the question");
```

- [ ] **Step 5: Verify.**

Run: `cd web && npx tsc --noEmit && npx vitest run src/components/PipelineDiagram.test.tsx`
Expected: clean types; PipelineDiagram tests PASS.

- [ ] **Step 6: Commit.**

```bash
git add web/src/components/PipelineDiagram.tsx web/src/styles/app.css web/src/components/PipelineDiagram.test.tsx
git commit -m "feat(web): in-box node descriptions + computed layout for tutor PipelineDiagram (parity with qa/chapter modals)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Visual tuning + verification (controller, on :5175)

Heights in `ROW_DEF` are estimates. After Task 1, open the tutor modal on :5175 and check:
- No node box overlaps the next; desc text isn't cut mid-graph awkwardly; arrows connect box edges cleanly.
- Loop-back arc (coverage→retrieval) still routes on the left.
- Toggle drafting workflow to "Orchestrator (per author)" → the worker cluster still lays out without overlap.
- Boxes now read like the qa/chapter modals (label + desc + model control).

If spacing is off, nudge the per-node `h` values in `ROW_DEF` (and re-run build) until clean, then amend/commit.

Run full suite once tuned: `cd web && npx vitest run && npm run build`.
