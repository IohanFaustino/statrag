# Non-tutor Mode Modals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Q&A, Facilitate, and Resume chat modes an info `(i)` modal that shows their pipeline structure and lets the user swap the model/provider per stage — matching the existing tutor modal — and add Gemini + Alibaba provider icons.

**Architecture:** Per-mode diagram components (`QAPipelineDiagram`, `ChapterPipelineDiagram`) render the existing `qaPipeline.ts` / `chapterPipeline.ts` data as a vertical list; each LLM node gets a `NodeModelDropdown` writing `stageModels[node.id]`. Three modals (`QAModeModal` remade, `ChapterFacilitateModal`, `ChapterResumeModal`) mirror `AboutModelModal`'s draft/Apply pattern and commit into the existing persisted `stageModels` dict. Stage keys are disjoint across modes, so one dict holds all overrides; the backend already reads per-stage keys. No backend changes.

**Tech Stack:** React 18 + TypeScript + Vite, Vitest (`renderToStaticMarkup` for component tests). Frontend only, under `web/`.

---

## Context for the implementer (read before starting)

- Run frontend tests: `cd web && npx vitest run <path>` (single file) or `npx vitest run` (all).
- Type/build check: `cd web && npx tsc --noEmit` then `npm run build`.
- The dev server is already running on :5175 (Vite) + :8766 (backend) via `./scripts/dev.sh`.
- **Node id == stage key** in both `web/src/data/qaPipeline.ts` (scope/retrieve/generate/verify) and `web/src/data/chapterPipeline.ts` (parse/fetch/resolve/map/stitch/ground). LLM nodes (`kind: "llm"`) are overridable; data nodes (`kind: "data"`, i.e. `retrieve` and `fetch`) show a fixed label.
- `NodeModelDropdown` (`web/src/components/NodeModelDropdown.tsx`) is reused as-is: props `{ value, providers, onChange, leadingOptions? }`. Its toggle shows the provider model **name** when `value` matches a model in `providers`, else the raw `value` string.
- `FocusModal` props: `{ open, onClose, size?, children, labelledBy?, panelClassName? }`.
- Existing tutor modal pattern to mirror: `web/src/components/modals/AboutModelModal.tsx`.
- Provider ids from the backend registry: `openai`, `deepseek`, `groq`, `google` (Gemini models), `alibaba` (Qwen models).
- Only **two** `ProviderIcon` functions exist: `web/src/components/ModelPicker.tsx` and `web/src/components/NodeModelDropdown.tsx`. (Topbar has none.)

---

## File Structure

New:
- `web/src/components/QAPipelineDiagram.tsx` — editable Q&A pipeline list.
- `web/src/components/QAPipelineDiagram.test.tsx`
- `web/src/components/ChapterPipelineDiagram.tsx` — editable chapter pipeline list (facilitate/resume).
- `web/src/components/ChapterPipelineDiagram.test.tsx`
- `web/src/components/modals/ChapterFacilitateModal.tsx`
- `web/src/components/modals/ChapterResumeModal.tsx`

Modified:
- `web/src/types.ts` — extend `ProviderId`.
- `web/src/components/ModelPicker.tsx` — add google/alibaba icons.
- `web/src/components/NodeModelDropdown.tsx` — add google/alibaba icons.
- `web/src/components/modals/QAModeModal.tsx` — remade editable.
- `web/src/components/ModePicker.tsx` — (i) buttons for facilitate/resume.
- `web/src/components/InputBar.tsx` — thread new about handlers.
- `web/src/App.tsx` — modal open flags + wiring + onApply.

Removed:
- `web/src/components/QAPipeline.tsx` — replaced by `QAPipelineDiagram`.

---

## Task 1: Provider icons (Gemini + Alibaba) and ProviderId type

**Files:**
- Modify: `web/src/types.ts:5`
- Modify: `web/src/components/NodeModelDropdown.tsx:7-35`
- Modify: `web/src/components/ModelPicker.tsx:12-44`
- Test: `web/src/components/NodeModelDropdown.test.tsx` (new)

- [ ] **Step 1: Write the failing test**

Create `web/src/components/NodeModelDropdown.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import NodeModelDropdown from "./NodeModelDropdown";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  {
    id: "google", name: "Google", short: "GAI", color: "#1A73E8",
    models: [{ id: "gemini-2.5-pro", name: "Gemini 2.5 Pro", tagline: "x", cost: "$$", speed: "fast", ctx: "1M" }],
  },
  {
    id: "alibaba", name: "Alibaba", short: "QW", color: "#FF6A00",
    models: [{ id: "qwen-max", name: "Qwen Max", tagline: "x", cost: "$$", speed: "fast", ctx: "32k" }],
  },
];

describe("NodeModelDropdown provider icons", () => {
  it("renders an icon for a google-provider model and shows its name", () => {
    const html = renderToStaticMarkup(
      <NodeModelDropdown value="gemini-2.5-pro" providers={PROVIDERS} onChange={() => {}} />,
    );
    expect(html).toContain("node-dd__icon");
    expect(html).toContain("Gemini 2.5 Pro");
    expect(html).toContain("<svg");
  });

  it("renders an icon for an alibaba-provider model and shows its name", () => {
    const html = renderToStaticMarkup(
      <NodeModelDropdown value="qwen-max" providers={PROVIDERS} onChange={() => {}} />,
    );
    expect(html).toContain("node-dd__icon");
    expect(html).toContain("Qwen Max");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/components/NodeModelDropdown.test.tsx`
Expected: FAIL — type error on provider `id: "google"` / `"alibaba"` (not assignable to `ProviderId`), or the icon falls through to the fallback dot. (The test asserting the name should pass; the type error blocks the run.)

- [ ] **Step 3a: Extend ProviderId**

In `web/src/types.ts`, change line 5:

```ts
export type ProviderId = "openai" | "deepseek" | "groq" | "google" | "alibaba";
```

- [ ] **Step 3b: Add icons to NodeModelDropdown.tsx**

In `web/src/components/NodeModelDropdown.tsx`, inside `function ProviderIcon`, add these two branches immediately before the final fallback `return` (after the `groq` branch, ~line 29):

```tsx
  if (id === "google") {
    // Gemini — four-point spark (Google AI mark, simplified)
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
        <path d="M12 2c.4 4.6 3.4 7.6 8 8-4.6.4-7.6 3.4-8 8-.4-4.6-3.4-7.6-8-8 4.6-.4 7.6-3.4 8-8Z" />
      </svg>
    );
  }
  if (id === "alibaba") {
    // Qwen / Alibaba — twin-peak mark (simplified)
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
        <path d="M7 3 3.2 13.2a1 1 0 0 0 .94 1.35H7.5L9.3 9.7l2.7 7.1a1 1 0 0 0 1.87 0l2.7-7.1 1.8 4.85h3.36a1 1 0 0 0 .94-1.35L19.36 3h-2.6l2.74 9H17.1l-2.2-5.9a1 1 0 0 0-1.87 0L10.83 12H8.34l2.74-9H7Z" />
      </svg>
    );
  }
```

- [ ] **Step 3c: Add the same two branches to ModelPicker.tsx**

In `web/src/components/ModelPicker.tsx`, inside its `function ProviderIcon`, add the identical two branches before the fallback `return` (after the `groq` branch, ~line 37). Use the exact same SVG markup as Step 3b.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/components/NodeModelDropdown.test.tsx`
Expected: PASS (both tests).

- [ ] **Step 5: Type-check + commit**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

```bash
git add web/src/types.ts web/src/components/NodeModelDropdown.tsx web/src/components/ModelPicker.tsx web/src/components/NodeModelDropdown.test.tsx
git commit -m "feat(web): add Gemini + Alibaba provider icons and ProviderId members

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: QAPipelineDiagram component

**Files:**
- Create: `web/src/components/QAPipelineDiagram.tsx`
- Test: `web/src/components/QAPipelineDiagram.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/src/components/QAPipelineDiagram.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import QAPipelineDiagram from "./QAPipelineDiagram";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  {
    id: "openai", name: "OpenAI", short: "OAI", color: "#10A37F",
    models: [{ id: "gpt-4o", name: "GPT-4o", tagline: "x", cost: "$$$", speed: "fast", ctx: "128k" }],
  },
];

describe("QAPipelineDiagram", () => {
  it("renders a swappable dropdown for each LLM node and a fixed label for the data node", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />,
    );
    // scope / generate / verify are llm → custom dropdown toggles
    expect(html).toContain("node-dd__toggle");
    expect(html).not.toContain("<select");
    // retrieve is a data node → fixed label, no dropdown for it
    expect(html).toContain("qa-pipeline__node--data");
    expect(html).toContain("text-embedding-3-large → RRF + rerank");
  });

  it("reflects a stageModels override on the matching node", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram
        providers={PROVIDERS}
        stageModels={{ generate: "gpt-4o" }}
        onStageModelChange={() => {}}
      />,
    );
    expect(html).toContain("GPT-4o");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/components/QAPipelineDiagram.test.tsx`
Expected: FAIL — "Cannot find module './QAPipelineDiagram'".

- [ ] **Step 3: Write the component**

Create `web/src/components/QAPipelineDiagram.tsx`:

```tsx
import { QA_PIPELINE } from "../data/qaPipeline";
import NodeModelDropdown from "./NodeModelDropdown";
import type { ModelProvider } from "../types";

interface QAPipelineDiagramProps {
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
}

/** Editable Q&A pipeline diagram for the mode's (i) modal. Each LLM node
 *  carries a per-stage model dropdown writing stageModels[node.id]. */
export default function QAPipelineDiagram({
  providers,
  stageModels,
  onStageModelChange,
}: QAPipelineDiagramProps) {
  return (
    <div className="qa-pipeline">
      <ol className="qa-pipeline__nodes">
        {QA_PIPELINE.nodes.map((n) => {
          const activeId = stageModels[n.id] ?? n.defaultModel;
          return (
            <li key={n.id} className={"qa-pipeline__node qa-pipeline__node--" + n.kind}>
              <div className="qa-pipeline__label">{n.label}</div>
              <div className="qa-pipeline__desc">{n.desc}</div>
              {n.kind === "llm" ? (
                <NodeModelDropdown
                  value={activeId}
                  providers={providers}
                  onChange={(id) => onStageModelChange(n.id, id)}
                />
              ) : (
                <div className="qa-pipeline__model">{n.defaultModel}</div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/components/QAPipelineDiagram.test.tsx`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/QAPipelineDiagram.tsx web/src/components/QAPipelineDiagram.test.tsx
git commit -m "feat(web): editable QAPipelineDiagram with per-stage model dropdowns

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Remake QAModeModal (editable) + wire into App

**Files:**
- Modify: `web/src/components/modals/QAModeModal.tsx` (full rewrite)
- Modify: `web/src/App.tsx:753-756` (QAModeModal render)

- [ ] **Step 1: Rewrite QAModeModal.tsx**

Replace the entire contents of `web/src/components/modals/QAModeModal.tsx`:

```tsx
import { useEffect, useState } from "react";
import FocusModal from "./FocusModal";
import QAPipelineDiagram from "../QAPipelineDiagram";
import type { ModelProvider } from "../../types";

interface QAModeModalProps {
  open: boolean;
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onApply(cfg: { stageModels: Record<string, string> }): void;
  onClose(): void;
}

// Q&A pipeline stages whose models are user-overridable.
const QA_STAGES = ["scope", "generate", "verify"] as const;

export default function QAModeModal({
  open,
  providers,
  stageModels,
  onApply,
  onClose,
}: QAModeModalProps) {
  const [draft, setDraft] = useState<Record<string, string>>(stageModels);

  // Re-seed the draft from the applied config each time the modal opens.
  useEffect(() => {
    if (open) setDraft(stageModels);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const dirty = QA_STAGES.some((s) => draft[s] !== stageModels[s]);
  const apply = () => {
    onApply({ stageModels: draft });
    onClose();
  };

  return (
    <FocusModal open={open} onClose={onClose} size="md" panelClassName="fm__panel--about" labelledBy="qa-modal-title">
      <div className="about-model">
        <header className="about-model__hd">
          <div>
            <h2 id="qa-modal-title" className="about-model__title">Q&amp;A mode</h2>
            <p className="about-model__blurb">Punctual Q&amp;A: scope → retrieve → generate → verify</p>
          </div>
          <button type="button" className="about-model__close" aria-label="Close" onClick={onClose}>✕</button>
        </header>

        <div className="about-model__body">
          <section className="about-model__section">
            <h3 className="about-model__sub">Pipeline — input → output</h3>
          </section>
          <QAPipelineDiagram
            providers={providers}
            stageModels={draft}
            onStageModelChange={(stage, id) => setDraft((prev) => ({ ...prev, [stage]: id }))}
          />
        </div>

        <footer className="about-model__footer">
          <span className="about-model__footer-hint">{dirty ? "Unsaved pipeline changes" : "No changes"}</span>
          <div className="about-model__footer-actions">
            <button type="button" className="about-model__btn about-model__btn--ghost" onClick={onClose}>Cancel</button>
            <button type="button" className="about-model__btn about-model__btn--apply" onClick={apply} disabled={!dirty}>Apply</button>
          </div>
        </footer>
      </div>
    </FocusModal>
  );
}
```

- [ ] **Step 2: Wire props in App.tsx**

In `web/src/App.tsx`, replace the `<QAModeModal …>` block (lines ~753-756):

```tsx
      <QAModeModal
        open={qaModalOpen}
        providers={providers}
        stageModels={stageModels}
        onApply={(cfg) => setStageModels((prev) => ({ ...prev, ...cfg.stageModels }))}
        onClose={() => setQaModalOpen(false)}
      />
```

- [ ] **Step 3: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors. (If `setStageModels` rejects the updater form, note its declared type at `App.tsx:179`; `usePersistentState` returns a `useState`-style setter that accepts an updater — the form above is valid.)

- [ ] **Step 4: Run the QA diagram test (regression) + commit**

Run: `cd web && npx vitest run src/components/QAPipelineDiagram.test.tsx`
Expected: PASS.

```bash
git add web/src/components/modals/QAModeModal.tsx web/src/App.tsx
git commit -m "feat(web): make Q&A modal editable with per-stage provider switch

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: ChapterPipelineDiagram component

**Files:**
- Create: `web/src/components/ChapterPipelineDiagram.tsx`
- Test: `web/src/components/ChapterPipelineDiagram.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/src/components/ChapterPipelineDiagram.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import ChapterPipelineDiagram from "./ChapterPipelineDiagram";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  {
    id: "openai", name: "OpenAI", short: "OAI", color: "#10A37F",
    models: [{ id: "gpt-4o", name: "GPT-4o", tagline: "x", cost: "$$$", speed: "fast", ctx: "128k" }],
  },
];

describe("ChapterPipelineDiagram", () => {
  it("renders dropdowns for LLM nodes and a fixed label for the fetch (data) node", () => {
    const html = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="facilitate" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />,
    );
    expect(html).toContain("node-dd__toggle");
    expect(html).not.toContain("<select");
    expect(html).toContain("qa-pipeline__node--data");
    expect(html).toContain("qdrant scroll (book + chapter filter)");
  });

  it("uses mode-specific copy on the map node", () => {
    const fac = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="facilitate" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />,
    );
    const res = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="resume" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />,
    );
    expect(fac).toContain("teach each section");
    expect(res).toContain("compress each section");
  });

  it("reflects a stageModels override on the matching node", () => {
    const html = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="resume" providers={PROVIDERS} stageModels={{ map: "gpt-4o" }} onStageModelChange={() => {}} />,
    );
    expect(html).toContain("GPT-4o");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/components/ChapterPipelineDiagram.test.tsx`
Expected: FAIL — "Cannot find module './ChapterPipelineDiagram'".

- [ ] **Step 3: Write the component**

Create `web/src/components/ChapterPipelineDiagram.tsx`:

```tsx
import { CHAPTER_PIPELINE } from "../data/chapterPipeline";
import NodeModelDropdown from "./NodeModelDropdown";
import type { ModelProvider } from "../types";

interface ChapterPipelineDiagramProps {
  mode: "facilitate" | "resume";
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
}

/** Editable chapter pipeline diagram, shared by the facilitate + resume
 *  modals. Both modes share the diagram shape; only the map-node note differs. */
export default function ChapterPipelineDiagram({
  mode,
  providers,
  stageModels,
  onStageModelChange,
}: ChapterPipelineDiagramProps) {
  const mapNote = mode === "facilitate" ? "teach each section" : "compress each section";
  return (
    <div className="qa-pipeline">
      <ol className="qa-pipeline__nodes">
        {CHAPTER_PIPELINE.nodes.map((n) => {
          const activeId = stageModels[n.id] ?? n.defaultModel;
          return (
            <li key={n.id} className={"qa-pipeline__node qa-pipeline__node--" + n.kind}>
              <div className="qa-pipeline__label">{n.label}</div>
              <div className="qa-pipeline__desc">{n.desc}</div>
              {n.id === "map" && <div className="qa-pipeline__sub">{mapNote}</div>}
              {n.kind === "llm" ? (
                <NodeModelDropdown
                  value={activeId}
                  providers={providers}
                  onChange={(id) => onStageModelChange(n.id, id)}
                />
              ) : (
                <div className="qa-pipeline__model">{n.defaultModel}</div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/components/ChapterPipelineDiagram.test.tsx`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/ChapterPipelineDiagram.tsx web/src/components/ChapterPipelineDiagram.test.tsx
git commit -m "feat(web): editable ChapterPipelineDiagram (facilitate/resume) with per-stage dropdowns

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Chapter modals (facilitate + resume)

**Files:**
- Create: `web/src/components/modals/ChapterFacilitateModal.tsx`
- Create: `web/src/components/modals/ChapterResumeModal.tsx`

- [ ] **Step 1: Create ChapterFacilitateModal.tsx**

```tsx
import { useEffect, useState } from "react";
import FocusModal from "./FocusModal";
import ChapterPipelineDiagram from "../ChapterPipelineDiagram";
import type { ModelProvider } from "../../types";

interface ChapterFacilitateModalProps {
  open: boolean;
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onApply(cfg: { stageModels: Record<string, string> }): void;
  onClose(): void;
}

// Chapter pipeline stages whose models are user-overridable.
const CHAPTER_STAGES = ["parse", "resolve", "map", "stitch", "ground"] as const;

export default function ChapterFacilitateModal({
  open,
  providers,
  stageModels,
  onApply,
  onClose,
}: ChapterFacilitateModalProps) {
  const [draft, setDraft] = useState<Record<string, string>>(stageModels);

  useEffect(() => {
    if (open) setDraft(stageModels);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const dirty = CHAPTER_STAGES.some((s) => draft[s] !== stageModels[s]);
  const apply = () => {
    onApply({ stageModels: draft });
    onClose();
  };

  return (
    <FocusModal open={open} onClose={onClose} size="md" panelClassName="fm__panel--about" labelledBy="facilitate-modal-title">
      <div className="about-model">
        <header className="about-model__hd">
          <div>
            <h2 id="facilitate-modal-title" className="about-model__title">Facilitate mode</h2>
            <p className="about-model__blurb">Ordered didactic walkthrough — teaches each section of the chapter in reading order.</p>
          </div>
          <button type="button" className="about-model__close" aria-label="Close" onClick={onClose}>✕</button>
        </header>

        <div className="about-model__body">
          <section className="about-model__section">
            <h3 className="about-model__sub">Pipeline — input → output</h3>
          </section>
          <ChapterPipelineDiagram
            mode="facilitate"
            providers={providers}
            stageModels={draft}
            onStageModelChange={(stage, id) => setDraft((prev) => ({ ...prev, [stage]: id }))}
          />
        </div>

        <footer className="about-model__footer">
          <span className="about-model__footer-hint">{dirty ? "Unsaved pipeline changes" : "No changes"}</span>
          <div className="about-model__footer-actions">
            <button type="button" className="about-model__btn about-model__btn--ghost" onClick={onClose}>Cancel</button>
            <button type="button" className="about-model__btn about-model__btn--apply" onClick={apply} disabled={!dirty}>Apply</button>
          </div>
        </footer>
      </div>
    </FocusModal>
  );
}
```

- [ ] **Step 2: Create ChapterResumeModal.tsx**

Identical to Step 1 except: component/interface name `ChapterResumeModal`, `labelledBy="resume-modal-title"`, the `id` on the `<h2>` is `resume-modal-title`, title text `Resume mode`, blurb `Ordered compressed recap — condenses each section of the chapter in reading order.`, and `<ChapterPipelineDiagram mode="resume" …>`.

```tsx
import { useEffect, useState } from "react";
import FocusModal from "./FocusModal";
import ChapterPipelineDiagram from "../ChapterPipelineDiagram";
import type { ModelProvider } from "../../types";

interface ChapterResumeModalProps {
  open: boolean;
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onApply(cfg: { stageModels: Record<string, string> }): void;
  onClose(): void;
}

const CHAPTER_STAGES = ["parse", "resolve", "map", "stitch", "ground"] as const;

export default function ChapterResumeModal({
  open,
  providers,
  stageModels,
  onApply,
  onClose,
}: ChapterResumeModalProps) {
  const [draft, setDraft] = useState<Record<string, string>>(stageModels);

  useEffect(() => {
    if (open) setDraft(stageModels);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const dirty = CHAPTER_STAGES.some((s) => draft[s] !== stageModels[s]);
  const apply = () => {
    onApply({ stageModels: draft });
    onClose();
  };

  return (
    <FocusModal open={open} onClose={onClose} size="md" panelClassName="fm__panel--about" labelledBy="resume-modal-title">
      <div className="about-model">
        <header className="about-model__hd">
          <div>
            <h2 id="resume-modal-title" className="about-model__title">Resume mode</h2>
            <p className="about-model__blurb">Ordered compressed recap — condenses each section of the chapter in reading order.</p>
          </div>
          <button type="button" className="about-model__close" aria-label="Close" onClick={onClose}>✕</button>
        </header>

        <div className="about-model__body">
          <section className="about-model__section">
            <h3 className="about-model__sub">Pipeline — input → output</h3>
          </section>
          <ChapterPipelineDiagram
            mode="resume"
            providers={providers}
            stageModels={draft}
            onStageModelChange={(stage, id) => setDraft((prev) => ({ ...prev, [stage]: id }))}
          />
        </div>

        <footer className="about-model__footer">
          <span className="about-model__footer-hint">{dirty ? "Unsaved pipeline changes" : "No changes"}</span>
          <div className="about-model__footer-actions">
            <button type="button" className="about-model__btn about-model__btn--ghost" onClick={onClose}>Cancel</button>
            <button type="button" className="about-model__btn about-model__btn--apply" onClick={apply} disabled={!dirty}>Apply</button>
          </div>
        </footer>
      </div>
    </FocusModal>
  );
}
```

- [ ] **Step 3: Type-check + commit**

Run: `cd web && npx tsc --noEmit`
Expected: no errors (modals not yet rendered — that's fine; they compile standalone).

```bash
git add web/src/components/modals/ChapterFacilitateModal.tsx web/src/components/modals/ChapterResumeModal.tsx
git commit -m "feat(web): facilitate + resume chapter modals (editable pipeline)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Wire (i) buttons + render modals

**Files:**
- Modify: `web/src/components/ModePicker.tsx` (props + facilitate/resume cells)
- Modify: `web/src/components/InputBar.tsx` (thread handlers)
- Modify: `web/src/App.tsx` (open flags + ModePicker handlers + render modals)

- [ ] **Step 1: ModePicker — add props**

In `web/src/components/ModePicker.tsx`, extend `ModePickerProps` (after `onAboutQA?(): void;`, ~line 27):

```tsx
  // Opens the Facilitate info modal (info icon lives on the Facilitate card).
  onAboutFacilitate?(): void;
  // Opens the Resume info modal (info icon lives on the Resume card).
  onAboutResume?(): void;
```

And update the destructure (line 30):

```tsx
export default function ModePicker({ activeMode, modes, onChange, onAbout, onAboutQA, onAboutFacilitate, onAboutResume }: ModePickerProps) {
```

- [ ] **Step 2: ModePicker — add facilitate/resume (i) cells**

In `web/src/components/ModePicker.tsx`, immediately after the `if (m.id === "qa" && onAboutQA) { … }` block (ends ~line 154, before `return item;`), insert:

```tsx
              // The Facilitate card carries an info (i) button → opens Facilitate modal.
              if (m.id === "facilitate" && onAboutFacilitate) {
                return (
                  <div key={m.id} className="mode-picker__cell">
                    {item}
                    <button
                      type="button"
                      className="mode-picker__about"
                      aria-label="About the Facilitate pipeline"
                      title="About the Facilitate pipeline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onAboutFacilitate();
                        setOpen(false);
                      }}
                    >
                      <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="8" cy="8" r="6.5" />
                        <path d="M8 7.2v4" strokeLinecap="round" />
                        <circle cx="8" cy="4.6" r="0.85" fill="currentColor" stroke="none" />
                      </svg>
                    </button>
                  </div>
                );
              }
              // The Resume card carries an info (i) button → opens Resume modal.
              if (m.id === "resume" && onAboutResume) {
                return (
                  <div key={m.id} className="mode-picker__cell">
                    {item}
                    <button
                      type="button"
                      className="mode-picker__about"
                      aria-label="About the Resume pipeline"
                      title="About the Resume pipeline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onAboutResume();
                        setOpen(false);
                      }}
                    >
                      <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="8" cy="8" r="6.5" />
                        <path d="M8 7.2v4" strokeLinecap="round" />
                        <circle cx="8" cy="4.6" r="0.85" fill="currentColor" stroke="none" />
                      </svg>
                    </button>
                  </div>
                );
              }
```

- [ ] **Step 3: InputBar — thread handlers**

In `web/src/components/InputBar.tsx`:

(a) Extend `InputBarProps` (after `onModeAboutQA?(): void;`, ~line 11):

```tsx
  onModeAboutFacilitate?(): void;
  onModeAboutResume?(): void;
```

(b) Add to the destructure (after `onModeAboutQA,`, ~line 21):

```tsx
  onModeAboutFacilitate,
  onModeAboutResume,
```

(c) Pass to `<ModePicker>` (after `onAboutQA={onModeAboutQA}`, ~line 96):

```tsx
            onAboutFacilitate={onModeAboutFacilitate}
            onAboutResume={onModeAboutResume}
```

- [ ] **Step 4: App.tsx — open flags**

In `web/src/App.tsx`, next to `const [qaModalOpen, setQaModalOpen] = useState(false);` (~line 178), add:

```tsx
  const [facilitateModalOpen, setFacilitateModalOpen] = useState(false);
  const [resumeModalOpen, setResumeModalOpen] = useState(false);
```

- [ ] **Step 5: App.tsx — pass handlers to InputBar**

In `web/src/App.tsx`, in the `<InputBar …>` block (after `onModeAboutQA={() => setQaModalOpen(true)}`, ~line 693):

```tsx
              onModeAboutFacilitate={() => setFacilitateModalOpen(true)}
              onModeAboutResume={() => setResumeModalOpen(true)}
```

- [ ] **Step 6: App.tsx — import + render the two chapter modals**

(a) Add imports near the other modal imports (after line 17 `import QAModeModal …`):

```tsx
import ChapterFacilitateModal from "./components/modals/ChapterFacilitateModal";
import ChapterResumeModal from "./components/modals/ChapterResumeModal";
```

(b) After the `<QAModeModal …/>` block (~line 756), add:

```tsx
      <ChapterFacilitateModal
        open={facilitateModalOpen}
        providers={providers}
        stageModels={stageModels}
        onApply={(cfg) => setStageModels((prev) => ({ ...prev, ...cfg.stageModels }))}
        onClose={() => setFacilitateModalOpen(false)}
      />

      <ChapterResumeModal
        open={resumeModalOpen}
        providers={providers}
        stageModels={stageModels}
        onApply={(cfg) => setStageModels((prev) => ({ ...prev, ...cfg.stageModels }))}
        onClose={() => setResumeModalOpen(false)}
      />
```

- [ ] **Step 7: Type-check + full test run**

Run: `cd web && npx tsc --noEmit && npx vitest run`
Expected: no type errors; all test files PASS (including existing `PipelineDiagram.test.tsx`, `qaPipeline.test.ts`, `chapterPipeline.test.ts`).

- [ ] **Step 8: Commit**

```bash
git add web/src/components/ModePicker.tsx web/src/components/InputBar.tsx web/src/App.tsx
git commit -m "feat(web): wire (i) modals for facilitate + resume modes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Remove dead QAPipeline + build + docs

**Files:**
- Delete: `web/src/components/QAPipeline.tsx`
- Modify: `docs/services/chat-features/51-qa-mode.md`
- Modify: chapter-modes feature doc (locate via grep below)
- Modify: `docs/system/changelog.md`

- [ ] **Step 1: Confirm QAPipeline has no remaining importers, then delete**

Run: `cd web && grep -rn "QAPipeline\b" src --include='*.tsx' --include='*.ts' | grep -v "QAPipelineDiagram"`
Expected: no output (the only former importer was `QAModeModal`, now using `QAPipelineDiagram`). If output appears, fix the importer first.

```bash
git rm web/src/components/QAPipeline.tsx
```

- [ ] **Step 2: Production build**

Run: `cd web && npm run build`
Expected: build succeeds, no TS errors, no unresolved imports.

- [ ] **Step 3: Update docs**

Locate the chapter-modes feature doc:

Run: `ls docs/services/chat-features/ | grep -iE "chapter|facilitate|resume"`

Then, in `docs/services/chat-features/51-qa-mode.md` and the chapter-modes doc, add/append a short note under the UI/modal section:

> The mode's `(i)` modal is now **editable**: each LLM stage exposes a per-stage model/provider dropdown (writes `ChatRequest.stageModels[<stage>]`), mirroring the tutor's About-model modal. The data stage (retrieval / chapter fetch) shows a fixed label. Stage keys are disjoint across modes, so overrides share the single persisted `statrag.stageModels` dict.

In `docs/system/changelog.md`, prepend an entry dated 2026-06-01:

```markdown
## 2026-06-01 — Editable mode modals (qa / facilitate / resume)

Q&A, Facilitate, and Resume modes now have an editable `(i)` modal with a
per-stage model/provider switch (new `QAPipelineDiagram` + `ChapterPipelineDiagram`
components; `QAModeModal` remade; new `ChapterFacilitateModal` + `ChapterResumeModal`).
Overrides write the shared `stageModels` dict (disjoint stage keys; backend
`_model_for` already supported per-stage overrides). Added Gemini (`google`) and
Alibaba (`alibaba`) provider icons + `ProviderId` members. Frontend-only.
```

- [ ] **Step 4: Commit**

```bash
git add -A docs/ web/src/components/QAPipeline.tsx
git commit -m "chore(web): drop dead QAPipeline; docs for editable mode modals

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Browser verification on :5175

**Files:** none (manual/automated browser check)

- [ ] **Step 1: Open the app and verify each modal**

With the dev server running (`./scripts/dev.sh`, :5175):
- Open the Mode picker. Confirm an `(i)` button appears on the **Q&A**, **Facilitate**, and **Resume** cards (tutor already has one).
- Click each `(i)`: a modal opens showing the pipeline as a vertical list. Each LLM stage shows a clickable model dropdown; the data stage shows a fixed label.
- Open a dropdown, pick a different provider/model (confirm Gemini + Alibaba groups show their icons). The footer flips to "Unsaved pipeline changes" and **Apply** enables.
- Press **Apply**, reopen the modal — the chosen model persists (reads back from `stageModels`). **Cancel** on a fresh edit discards.

- [ ] **Step 2: Confirm no console errors**

Check the browser console — no React warnings/errors from the new components.

- [ ] **Step 3: Final commit (if any tweaks were needed)**

Only if Step 1-2 surfaced fixes. Otherwise this task is verification-only.

---

## Self-review notes

- **Spec coverage:** diagram components (T2,T4), editable modals (T3,T5), ModePicker `(i)` + App wiring (T6), provider SVGs + ProviderId (T1), dead-code removal + docs (T7), browser verify (T8). All spec sections mapped.
- **Type consistency:** `onStageModelChange(stage: string, modelId: string)` used identically in both diagrams and their modals; `onApply(cfg: { stageModels: Record<string,string> })` identical across the three modals; `stageModels: Record<string,string>` matches `App.tsx` state type.
- **Correction vs spec:** spec listed three `ProviderIcon` functions; only **two** exist (Topbar has none) — Task 1 edits two files.
