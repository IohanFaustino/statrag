# Non-tutor Modal → Tutor Parity Implementation Plan

> **For agentic workers:** Execute task-by-task. Frontend only, under `web/`. React 18 + TS + Vite, Vitest (`renderToStaticMarkup`).

**Goal:** Make the Q&A / Facilitate / Resume mode modals match the tutor modal's full layout — title + blurb + **description** + **Features list** + a **connected node-graph** (boxes joined by arrows, with Question/output I/O nodes) — instead of the current bare numbered list.

**Architecture:** One reusable `FlowDiagram` renders a linear pipeline as a vertical column of tutor-style `pipe2` node boxes joined by centered down-arrow connectors, bracketed by dashed I/O nodes. `QAPipelineDiagram` + `ChapterPipelineDiagram` become thin adapters mapping their `*Pipeline.ts` data → `FlowNode[]` and rendering `FlowDiagram`. New `qaMode.ts` / `chapterMode.ts` metadata (mirroring `tutorMode.ts`) supply description + features. The three modals render description + Features sections like `AboutModelModal`. Backend untouched; per-node dropdowns still write the shared `stageModels`.

**Tech Stack:** React+TS, reusing existing `pipe2` CSS + `NodeModelDropdown`.

---

## Context for the implementer

- Tests: `cd web && npx vitest run <path>`. Type-check: `cd web && npx tsc --noEmit`. Build: `cd web && npm run build`.
- Reference modal to match: `web/src/components/modals/AboutModelModal.tsx` (header → body: `about-model__desc`, Features `about-model__section`/`about-model__caps`/`about-model__cap`, "Pipeline — input → output" `about-model__sub`, diagram → footer).
- Reference metadata: `web/src/data/tutorMode.ts` (`TUTOR_MODE` = title, blurb, description, features[{label, detail}]).
- Reuse `pipe2` node classes (already in `web/src/styles/app.css` ~line 2517): `.pipe2`, `.pipe2__node`, `.pipe2__node--io` (dashed), `.pipe2__node--llm` (accent left border), `.pipe2__node-hd`, `.pipe2__node-label`, `.pipe2__badge`, `.pipe2__model-fixed`.
- `NodeModelDropdown` props: `{ value, providers, onChange, leadingOptions? }`.
- Pipeline data: `web/src/data/qaPipeline.ts` (`QA_PIPELINE.nodes`: scope/retrieve/generate/verify; node id == stage key; kind llm|data) and `web/src/data/chapterPipeline.ts` (`CHAPTER_PIPELINE.nodes`: parse/fetch/resolve/map/stitch/ground).
- IMPORTANT git hygiene: the branch is shared with a concurrent docs(html) session. When committing, `git add` ONLY the explicit files for the task. NEVER `git add -A`/`.`/`commit -a`.

---

## Task 1: Mode metadata (qaMode.ts, chapterMode.ts)

**Files:** Create `web/src/data/qaMode.ts`, `web/src/data/chapterMode.ts`.

- [ ] **Step 1: Create `web/src/data/qaMode.ts`**

```ts
// Description of the Q&A mode itself (the modal opens from the Q&A card).
export const QA_MODE = {
  title: "Q&A mode",
  blurb: "Punctual, source-grounded answers",
  description:
    "Q&A mode answers a single, focused question with a terse, directly-grounded reply built only from the indexed books. It narrows your question to the actual gap, retrieves a small high-precision set of sources, writes a scoped answer that skips what you already know, and audits each claim against the sources.",
  features: [
    { label: "Gap-scoped", detail: "Parses your question into {target gap, assumed-known, answer form} so it answers only what's missing." },
    { label: "High-precision retrieval", detail: "Hybrid dense + sparse search reranked to a small top-k for focused, low-noise context." },
    { label: "Per-claim citations", detail: "Each statement is attributed to the source book it came from." },
    { label: "Grounding verify", detail: "Audits claims against the sources and sets a confidence badge; advisory, never blocks the answer." },
    { label: "Configurable pipeline", detail: "Swap the model used at each LLM stage in the diagram below." },
  ],
} as const;
```

- [ ] **Step 2: Create `web/src/data/chapterMode.ts`**

```ts
// Descriptions of the two chapter modes (modals open from the Facilitate /
// Resume cards). Both share the chapter pipeline; framing differs.
export const FACILITATE_MODE = {
  title: "Facilitate mode",
  blurb: "Ordered didactic walkthrough",
  description:
    "Facilitate mode teaches a whole chapter (or chosen subtopics) in the author's reading order. It fetches every section structurally — no relevance search — then teaches each section in turn, threading a running context so ideas build exactly as the book intended.",
  features: [
    { label: "Structural fetch", detail: "Pulls the chapter's sections from Qdrant by book+chapter filter, ordered by page — not by relevance." },
    { label: "Reading-order preserved", detail: "Sections are never reordered; the digest follows the chapter's own sequence." },
    { label: "Subtopic resolve", detail: "Maps the subtopics you named to the chapter's real headings (closest-match + confirm); empty = whole chapter." },
    { label: "Teach each section", detail: "Per-section didactic pass with a running context so ideas connect across sections." },
    { label: "Grounded + stitched", detail: "Adds a short intro/outro and audits the digest against the sources." },
    { label: "Configurable pipeline", detail: "Swap the model used at each LLM stage in the diagram below." },
  ],
} as const;

export const RESUME_MODE = {
  title: "Resume mode",
  blurb: "Ordered compressed recap",
  description:
    "Resume mode condenses a whole chapter (or chosen subtopics) into a compact recap that follows the author's reading order. It fetches every section structurally — no relevance search — then compresses each section in turn so you get a faithful, ordered summary.",
  features: [
    { label: "Structural fetch", detail: "Pulls the chapter's sections from Qdrant by book+chapter filter, ordered by page — not by relevance." },
    { label: "Reading-order preserved", detail: "Sections are never reordered; the recap follows the chapter's own sequence." },
    { label: "Subtopic resolve", detail: "Maps the subtopics you named to the chapter's real headings (closest-match + confirm); empty = whole chapter." },
    { label: "Compress each section", detail: "Per-section compact pass keeping the key result of each part." },
    { label: "Grounded + stitched", detail: "Adds a short intro/outro and audits the recap against the sources." },
    { label: "Configurable pipeline", detail: "Swap the model used at each LLM stage in the diagram below." },
  ],
} as const;
```

- [ ] **Step 3: Type-check + commit**

Run: `cd web && npx tsc --noEmit` → clean.

```bash
git add web/src/data/qaMode.ts web/src/data/chapterMode.ts
git commit -m "feat(web): mode metadata (description + features) for qa/facilitate/resume

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: FlowDiagram component + CSS

**Files:** Create `web/src/components/FlowDiagram.tsx`, `web/src/components/FlowDiagram.test.tsx`; modify `web/src/styles/app.css`.

- [ ] **Step 1: Write the failing test** — `web/src/components/FlowDiagram.test.tsx`

```tsx
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import FlowDiagram, { type FlowNode } from "./FlowDiagram";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  { id: "openai", name: "OpenAI", short: "OAI", color: "#10A37F",
    models: [{ id: "gpt-4o", name: "GPT-4o", tagline: "x", cost: "$$$", speed: "fast", ctx: "128k" }] },
];

const NODES: FlowNode[] = [
  { id: "scope", label: "Scope extract", desc: "narrows the gap", kind: "llm", defaultModel: "gpt-5.4-nano-2026-03-17" },
  { id: "retrieve", label: "Hybrid retrieval", desc: "dense + sparse", kind: "data", defaultModel: "text-embedding-3-large" },
];

describe("FlowDiagram", () => {
  it("renders dashed io nodes for input + output labels", () => {
    const html = renderToStaticMarkup(
      <FlowDiagram nodes={NODES} inputLabel="Question" outputLabel="Answer"
        providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(html).toContain("pipe2__node--io");
    expect(html).toContain("Question");
    expect(html).toContain("Answer");
  });
  it("renders a dropdown for llm nodes and a fixed label for data nodes, with connectors", () => {
    const html = renderToStaticMarkup(
      <FlowDiagram nodes={NODES} inputLabel="Question" outputLabel="Answer"
        providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(html).toContain("node-dd__toggle");          // llm scope
    expect(html).toContain("pipe2__model-fixed");        // data retrieve
    expect(html).toContain("text-embedding-3-large");
    expect(html).toContain("flow__arrow");               // connectors present
    expect(html).toContain("narrows the gap");           // desc rendered
  });
  it("reflects a stageModels override", () => {
    const html = renderToStaticMarkup(
      <FlowDiagram nodes={NODES} inputLabel="Q" outputLabel="A"
        providers={PROVIDERS} stageModels={{ scope: "gpt-4o" }} onStageModelChange={() => {}} />);
    expect(html).toContain("GPT-4o");
  });
});
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd web && npx vitest run src/components/FlowDiagram.test.tsx`
Expected: FAIL — "Cannot find module './FlowDiagram'".

- [ ] **Step 3: Write `web/src/components/FlowDiagram.tsx`**

```tsx
import NodeModelDropdown from "./NodeModelDropdown";
import type { ModelProvider } from "../types";

export interface FlowNode {
  id: string;
  label: string;
  desc: string;
  kind: "llm" | "data";
  /** per-stage model override key; defaults to id. */
  stageKey?: string;
  defaultModel: string;
}

interface FlowDiagramProps {
  nodes: FlowNode[];
  inputLabel: string;
  outputLabel: string;
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
}

/** Centered down-arrow connector between two flow nodes. */
function Connector() {
  return (
    <div className="flow__arrow" aria-hidden="true">
      <svg viewBox="0 0 12 26" width="12" height="26" fill="none"
        stroke="var(--text-tertiary, #888)" strokeWidth="1.4">
        <path d="M6 0 V20" strokeOpacity="0.55" />
        <path d="M2 16 L6 21 L10 16" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.85" />
      </svg>
    </div>
  );
}

/** Generic vertical flow-graph for a linear pipeline. Reuses the tutor
 *  `pipe2` node visual language: dashed io boxes top/bottom, llm/data node
 *  boxes joined by centered down-arrow connectors. Each llm node carries a
 *  per-stage model dropdown; data nodes show a fixed model label. */
export default function FlowDiagram({
  nodes, inputLabel, outputLabel, providers, stageModels, onStageModelChange,
}: FlowDiagramProps) {
  return (
    <div className="pipe2 flow" role="group" aria-label="Pipeline — input to output">
      <div className="pipe2__node pipe2__node--io flow__node">
        <div className="pipe2__node-hd"><span className="pipe2__node-label">{inputLabel}</span></div>
      </div>
      {nodes.map((n) => {
        const stage = n.stageKey ?? n.id;
        const activeId = stageModels[stage] ?? n.defaultModel;
        return (
          <div key={n.id} className="flow__seg">
            <Connector />
            <div className={"pipe2__node flow__node pipe2__node--" + n.kind}>
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
                {n.kind === "llm"
                  ? <span className="pipe2__badge" title="Click the model to swap">swap</span>
                  : <span className="pipe2__badge pipe2__badge--data" title="Fixed data stage">data</span>}
              </div>
              <div className="pipe2__node-desc">{n.desc}</div>
              {n.kind === "llm" ? (
                <NodeModelDropdown
                  value={activeId}
                  providers={providers}
                  onChange={(id) => onStageModelChange(stage, id)}
                />
              ) : (
                <span className="pipe2__model-fixed">{n.defaultModel}</span>
              )}
            </div>
          </div>
        );
      })}
      <Connector />
      <div className="pipe2__node pipe2__node--io flow__node">
        <div className="pipe2__node-hd"><span className="pipe2__node-label">{outputLabel}</span></div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Add CSS** — append to `web/src/styles/app.css` after the `.pipe2__model-fixed` block (~line 2562, before the `/* Node model dropdown */` section):

```css
/* ─── Flow diagram (linear pipeline for qa / chapter mode modals) ─────── */
.flow { display: flex; flex-direction: column; align-items: center; width: 100%; max-width: 320px; margin: 16px auto 0; }
.flow__node { width: 100%; }
.flow__seg { width: 100%; display: flex; flex-direction: column; align-items: center; }
.flow__arrow { display: flex; justify-content: center; line-height: 0; margin: 1px 0; }
.pipe2__node-desc { font-size: 0.74rem; color: var(--text-tertiary, #9aa1aa); line-height: 1.45; }
.pipe2__badge--data { color: var(--text-tertiary, #9aa1aa); border-color: var(--text-tertiary, #9aa1aa); }
```

- [ ] **Step 5: Run test, verify pass**

Run: `cd web && npx vitest run src/components/FlowDiagram.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add web/src/components/FlowDiagram.tsx web/src/components/FlowDiagram.test.tsx web/src/styles/app.css
git commit -m "feat(web): reusable FlowDiagram (tutor-style node-graph) + flow css

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Adapt QAPipelineDiagram + ChapterPipelineDiagram to FlowDiagram

**Files:** Modify `web/src/components/QAPipelineDiagram.tsx`, `web/src/components/ChapterPipelineDiagram.tsx`, and their test files.

- [ ] **Step 1: Rewrite `web/src/components/QAPipelineDiagram.tsx`** (keep public props identical; render via FlowDiagram)

```tsx
import { QA_PIPELINE } from "../data/qaPipeline";
import FlowDiagram, { type FlowNode } from "./FlowDiagram";
import type { ModelProvider } from "../types";

interface QAPipelineDiagramProps {
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
}

const QA_NODES: FlowNode[] = QA_PIPELINE.nodes.map((n) => ({
  id: n.id, label: n.label, desc: n.desc, kind: n.kind, defaultModel: n.defaultModel,
}));

/** Editable Q&A pipeline graph for the mode's (i) modal. */
export default function QAPipelineDiagram({ providers, stageModels, onStageModelChange }: QAPipelineDiagramProps) {
  return (
    <FlowDiagram
      nodes={QA_NODES}
      inputLabel="Question"
      outputLabel="Answer"
      providers={providers}
      stageModels={stageModels}
      onStageModelChange={onStageModelChange}
    />
  );
}
```

- [ ] **Step 2: Rewrite `web/src/components/ChapterPipelineDiagram.tsx`** (map note folded into the `map` node desc)

```tsx
import { CHAPTER_PIPELINE } from "../data/chapterPipeline";
import FlowDiagram, { type FlowNode } from "./FlowDiagram";
import type { ModelProvider } from "../types";

interface ChapterPipelineDiagramProps {
  mode: "facilitate" | "resume";
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
}

/** Editable chapter pipeline graph, shared by the facilitate + resume modals.
 *  Both share the pipeline shape; only the map-node note differs by mode. */
export default function ChapterPipelineDiagram({
  mode, providers, stageModels, onStageModelChange,
}: ChapterPipelineDiagramProps) {
  const mapNote = mode === "facilitate" ? "teach each section" : "compress each section";
  const nodes: FlowNode[] = CHAPTER_PIPELINE.nodes.map((n) => ({
    id: n.id,
    label: n.label,
    desc: n.id === "map" ? `${n.desc} (${mapNote})` : n.desc,
    kind: n.kind,
    defaultModel: n.defaultModel,
  }));
  return (
    <FlowDiagram
      nodes={nodes}
      inputLabel="Chapter + subtopics"
      outputLabel="Chapter digest"
      providers={providers}
      stageModels={stageModels}
      onStageModelChange={onStageModelChange}
    />
  );
}
```

- [ ] **Step 3: Update `web/src/components/QAPipelineDiagram.test.tsx`** (assert new flow markup)

```tsx
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import QAPipelineDiagram from "./QAPipelineDiagram";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  { id: "openai", name: "OpenAI", short: "OAI", color: "#10A37F",
    models: [{ id: "gpt-4o", name: "GPT-4o", tagline: "x", cost: "$$$", speed: "fast", ctx: "128k" }] },
];

describe("QAPipelineDiagram", () => {
  it("renders io nodes and a dropdown per llm stage, fixed label for the data stage", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(html).toContain("pipe2__node--io");
    expect(html).toContain("Question");
    expect(html).toContain("Answer");
    expect(html).toContain("node-dd__toggle");                       // llm nodes
    expect(html).toContain("pipe2__model-fixed");                    // retrieve (data)
    expect(html).toContain("text-embedding-3-large &#x2192; RRF + rerank");
    expect(html).not.toContain("<select");
  });
  it("reflects a stageModels override", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram providers={PROVIDERS} stageModels={{ generate: "gpt-4o" }} onStageModelChange={() => {}} />);
    expect(html).toContain("GPT-4o");
  });
});
```

Note: the data-node label text "text-embedding-3-large → RRF + rerank" contains a `→`; in static markup the arrow renders as the literal char. If the `&#x2192;` assertion fails, replace that line with `expect(html).toContain("RRF + rerank");` (simpler, avoids entity-encoding ambiguity). Prefer the simpler form.

- [ ] **Step 4: Update `web/src/components/ChapterPipelineDiagram.test.tsx`**

```tsx
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import ChapterPipelineDiagram from "./ChapterPipelineDiagram";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  { id: "openai", name: "OpenAI", short: "OAI", color: "#10A37F",
    models: [{ id: "gpt-4o", name: "GPT-4o", tagline: "x", cost: "$$$", speed: "fast", ctx: "128k" }] },
];

describe("ChapterPipelineDiagram", () => {
  it("renders io nodes, dropdowns for llm stages, fixed label for fetch (data)", () => {
    const html = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="facilitate" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(html).toContain("pipe2__node--io");
    expect(html).toContain("Chapter digest");
    expect(html).toContain("node-dd__toggle");
    expect(html).toContain("pipe2__model-fixed");
    expect(html).toContain("qdrant scroll (book + chapter filter)");
    expect(html).not.toContain("<select");
  });
  it("uses mode-specific copy on the map node", () => {
    const fac = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="facilitate" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    const res = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="resume" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(fac).toContain("teach each section");
    expect(res).toContain("compress each section");
  });
  it("reflects a stageModels override", () => {
    const html = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="resume" providers={PROVIDERS} stageModels={{ map: "gpt-4o" }} onStageModelChange={() => {}} />);
    expect(html).toContain("GPT-4o");
  });
});
```

- [ ] **Step 5: Run both tests, verify pass**

Run: `cd web && npx vitest run src/components/QAPipelineDiagram.test.tsx src/components/ChapterPipelineDiagram.test.tsx`
Expected: PASS. (If the QA data-label assertion fails on entity encoding, switch it to `"RRF + rerank"` as noted.)

- [ ] **Step 6: Commit**

```bash
git add web/src/components/QAPipelineDiagram.tsx web/src/components/ChapterPipelineDiagram.tsx web/src/components/QAPipelineDiagram.test.tsx web/src/components/ChapterPipelineDiagram.test.tsx
git commit -m "refactor(web): render qa/chapter diagrams via FlowDiagram (tutor-style graph)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Add description + Features to the three modals

**Files:** Modify `web/src/components/modals/QAModeModal.tsx`, `web/src/components/modals/ChapterFacilitateModal.tsx`, `web/src/components/modals/ChapterResumeModal.tsx`.

For each modal: import its metadata; replace the hardcoded title/blurb with `META.title` / `META.blurb`; insert a description paragraph + Features section before the "Pipeline — input → output" heading, mirroring `AboutModelModal`.

- [ ] **Step 1: QAModeModal** — add `import { QA_MODE } from "../../data/qaMode";`. Replace the header title/blurb text with `{QA_MODE.title}` / `{QA_MODE.blurb}`. Inside `about-model__body`, BEFORE the existing `about-model__section` that holds the "Pipeline — input → output" `<h3>`, insert:

```tsx
          <p className="about-model__desc">{QA_MODE.description}</p>

          <section className="about-model__section">
            <h3 className="about-model__sub">Features</h3>
            <ul className="about-model__caps">
              {QA_MODE.features.map((f) => (
                <li key={f.label} className="about-model__cap">
                  <strong>{f.label}:</strong> {f.detail}
                </li>
              ))}
            </ul>
          </section>
```

- [ ] **Step 2: ChapterFacilitateModal** — `import { FACILITATE_MODE } from "../../data/chapterMode";`. Use `{FACILITATE_MODE.title}` / `{FACILITATE_MODE.blurb}` in the header. Insert the identical description + Features block (using `FACILITATE_MODE`) before the "Pipeline — input → output" section.

- [ ] **Step 3: ChapterResumeModal** — `import { RESUME_MODE } from "../../data/chapterMode";`. Use `{RESUME_MODE.title}` / `{RESUME_MODE.blurb}` in the header. Insert the description + Features block (using `RESUME_MODE`) before the "Pipeline — input → output" section.

- [ ] **Step 4: Type-check + full test run + build**

Run: `cd web && npx tsc --noEmit && npx vitest run && npm run build`
Expected: clean types; all tests pass; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/modals/QAModeModal.tsx web/src/components/modals/ChapterFacilitateModal.tsx web/src/components/modals/ChapterResumeModal.tsx
git commit -m "feat(web): tutor-parity layout for qa/facilitate/resume modals (desc + features)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Browser verification on :5175

- [ ] Open each mode's `(i)` modal on :5175. Confirm each now shows: title + blurb, a description paragraph, a Features list, then a connected node-graph (dashed Question/output I/O boxes top+bottom, node boxes joined by down-arrows, llm nodes with model dropdowns incl. Google/Alibaba, data nodes fixed). Confirm structure visually parallels the tutor modal. Open a dropdown, change a model → footer flips to "Unsaved pipeline changes", Apply enables. Cancel discards. No console errors.

---

## Self-review notes

- **Coverage:** description + Features (Task 1 metadata + Task 4 modals); connected node-graph (Task 2 FlowDiagram + Task 3 adapters); I/O nodes + arrows (FlowDiagram). All gaps vs tutor addressed.
- **Type consistency:** `FlowNode` shape `{id,label,desc,kind,stageKey?,defaultModel}`; adapters map `*Pipeline.ts` nodes into it; `onStageModelChange(stage,id)` and `stageModels: Record<string,string>` unchanged from prior tasks. Modal props unchanged (QAPipelineDiagram/ChapterPipelineDiagram keep their signatures), so App wiring untouched.
- **No backend / no schema / no App.tsx changes.**
