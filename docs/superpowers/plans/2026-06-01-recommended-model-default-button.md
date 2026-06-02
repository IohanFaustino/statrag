# Recommended Model + "Default" Button Implementation Plan

> Frontend + a small backend registry change. Define **qwen-plus** as the single system-recommended model, make it the picker default, surface a "recommended" badge, and add a **Default** button beside Apply in all four mode modals that sets every swappable LLM stage to the recommended model.

**Goal:**
1. Mark `qwen-plus` as the system-recommended model in the registry (single source of truth) and expose it via `/api/models`.
2. Make qwen-plus the frontend picker default (replacing gpt-4o) and the unknown-model fallback.
3. Show a small "★ recommended" badge on the flagged model in the model dropdowns.
4. Add a **Default** button next to Apply in the tutor, Q&A, Facilitate, and Resume modals; clicking it fills the modal's draft so every swappable LLM stage = the recommended model (dirty → user presses Apply to commit). Tutor's choice nodes (author-diversity, drafting-workflow) are left unchanged.

**Architecture:** Backend `Model` schema gains `recommended: bool = False`; `qwen-plus` sets it true. `/api/models` already returns the registry, so the flag flows to the client. Frontend derives the recommended id at runtime from `providers` (the flagged model) for the badge + Default button; a static `RECOMMENDED_MODEL_ID = "qwen-plus"` constant is used where a compile-time default is needed (App's persisted default). The Default button mutates each modal's existing draft `stageModels` state.

**Tech Stack:** Python/pydantic (backend), React+TS+Vite, Vitest.

---

## Context

- Backend Model schema: `src/services/chat/schemas/_core.py:91` (`class Model(BaseModel)` — id/name/tagline/cost/speed/ctx). ProviderId already includes google/alibaba.
- Registry: `src/services/chat/llm/router.py` — `qwen-plus` Model at ~line 179; `list_providers()` at 314; route `@router.get("/models")` at 331.
- Frontend Model type: `web/src/types.ts` (`interface Model`). Provider fetch: `web/src/api/client.ts` `fetchProviders()` → `/api/models`.
- Provider icons / dropdown rows: `web/src/components/NodeModelDropdown.tsx` (per-node, used in diagrams) and `web/src/components/ModelPicker.tsx` (chatbox picker).
- App state: `web/src/App.tsx:175` `activeModel` default `"gpt-4o"`; unknown-model fallback at ~332 (`setActiveModel(allIds[0])`).
- Modals: `web/src/components/modals/AboutModelModal.tsx` (tutor; draft = `draftStageModels`/`draftDiversity`/`draftWorkflow`), `QAModeModal.tsx`, `ChapterFacilitateModal.tsx`, `ChapterResumeModal.tsx` (each has `draft` `Record<string,string>`). Footer is `about-model__footer` with `about-model__btn--ghost` (Cancel) + `about-model__btn--apply` (Apply).
- Swappable stage keys per modal:
  - tutor: `expansion`, `image_judge`, `plan`, `draft`, `vision_explain` (the `StageKey` union in `web/src/data/tutorPipeline.ts`).
  - qa: `scope`, `generate`, `verify`.
  - facilitate/resume: `parse`, `resolve`, `map`, `stitch`, `ground`.
- git hygiene: branch shared with a concurrent docs session. `git add` ONLY explicit paths. NEVER `git add -A`/`.`/`commit -a`.

---

## Task 1: Backend — recommended flag on qwen-plus

**Files:** `src/services/chat/schemas/_core.py`, `src/services/chat/llm/router.py`.

- [ ] **Step 1:** In `_core.py`, add a field to `class Model`:

```python
class Model(BaseModel):
    id: str
    name: str
    tagline: str
    cost: str
    speed: str
    ctx: str
    recommended: bool = False
```

- [ ] **Step 2:** In `router.py`, set `recommended=True` on the `qwen-plus` Model entry (only that one):

```python
            Model(
                id="qwen-plus",
                name="Qwen Plus",
                tagline="Cheap 1M-ctx — prime draft candidate",
                cost="$",
                speed="fast",
                ctx="1M",
                recommended=True,
            ),
```

- [ ] **Step 3:** Verify the API serializes it.

Run: `curl -s http://localhost:8766/api/models | python3 -c "import sys,json; d=json.load(sys.stdin); print([m['id'] for p in d for m in p['models'] if m.get('recommended')])"`
Expected: `['qwen-plus']`. (Backend `--reload` picks up the change; if not, the dev server restarts on save.)

- [ ] **Step 4: Commit.**

```bash
git add src/services/chat/schemas/_core.py src/services/chat/llm/router.py
git commit -m "feat(chat): mark qwen-plus as the system-recommended model in the registry

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Frontend — type, constant, default, derive helper

**Files:** `web/src/types.ts`, `web/src/data/recommended.ts` (new), `web/src/App.tsx`.

- [ ] **Step 1:** In `web/src/types.ts`, add `recommended` to `interface Model`:

```ts
export interface Model {
  id: string; name: string; tagline: string;
  cost: string; speed: string; ctx: string;
  recommended?: boolean;
}
```

- [ ] **Step 2:** Create `web/src/data/recommended.ts`:

```ts
import type { ModelProvider } from "../types";

// The system-recommended model id. Must match the registry entry flagged
// `recommended: true` in src/services/chat/llm/router.py (qwen-plus).
export const RECOMMENDED_MODEL_ID = "qwen-plus";

/** The recommended model id from the live registry (the model flagged
 *  `recommended`), falling back to the static constant. */
export function recommendedModelId(providers: ModelProvider[]): string {
  for (const p of providers) {
    const m = p.models.find((mm) => mm.recommended);
    if (m) return m.id;
  }
  return RECOMMENDED_MODEL_ID;
}
```

- [ ] **Step 3:** In `web/src/App.tsx`:
  - Import: `import { RECOMMENDED_MODEL_ID, recommendedModelId } from "./data/recommended";`
  - Change the `activeModel` default (line ~175) from `"gpt-4o"` to `RECOMMENDED_MODEL_ID`:

```ts
  const [activeModel, setActiveModel] = usePersistentState<string>("statrag.activeModel", RECOMMENDED_MODEL_ID);
```

  - In the providers-load effect (the `if (!allIds.includes(activeModel) …)` block, ~line 332), prefer the recommended model on fallback:

```ts
          if (!allIds.includes(activeModel) && allIds.length > 0) {
            const rec = recommendedModelId(data);
            setActiveModel(allIds.includes(rec) ? rec : allIds[0]);
          }
```

  - Compute the recommended id once for the modals (near other derived values):

```ts
  const recommendedModel = recommendedModelId(providers);
```

- [ ] **Step 4:** Type-check.

Run: `cd web && npx tsc --noEmit` → clean.

- [ ] **Step 5: Commit.**

```bash
git add web/src/types.ts web/src/data/recommended.ts web/src/App.tsx
git commit -m "feat(web): default the picker to the recommended model (qwen-plus)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Recommended badge in the model dropdowns

**Files:** `web/src/components/NodeModelDropdown.tsx`, `web/src/components/ModelPicker.tsx`, `web/src/styles/app.css`.

- [ ] **Step 1: NodeModelDropdown** — in the provider-group model rows (`p.models.map((m) => …)`), append a badge when `m.recommended`. After the `node-dd__row-name` span inside the row button:

```tsx
                    <span className="node-dd__row-name">{m.name}</span>
                    {m.recommended && <span className="node-dd__rec" title="System-recommended">★</span>}
```

(Place it before the existing `active` checkmark `<svg>`.)

- [ ] **Step 2: ModelPicker** — in its model row rendering, add the same badge next to the model name when `m.recommended`. Match the existing row markup; add:

```tsx
                            {m.recommended && <span className="mp-row__rec" title="System-recommended">★</span>}
```

(Locate the model-name span in the `p.models.map(...)` row and place the badge right after it. Use the existing row's class names as the sibling reference.)

- [ ] **Step 3: CSS** — append to `web/src/styles/app.css`:

```css
.node-dd__rec, .mp-row__rec {
  margin-left: 6px; font-size: 0.7rem; line-height: 1;
  color: var(--accent-green, #3fb950);
  flex-shrink: 0;
}
```

- [ ] **Step 4: Verify build + type.**

Run: `cd web && npx tsc --noEmit && npm run build` → clean + succeeds.

- [ ] **Step 5: Commit.**

```bash
git add web/src/components/NodeModelDropdown.tsx web/src/components/ModelPicker.tsx web/src/styles/app.css
git commit -m "feat(web): show a recommended (★) badge on the flagged model in pickers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: "Default" button in all four modals

**Files:** `web/src/components/modals/AboutModelModal.tsx`, `QAModeModal.tsx`, `ChapterFacilitateModal.tsx`, `ChapterResumeModal.tsx`, and `web/src/App.tsx` (pass `recommendedModel`).

Each modal: add a `recommendedModel: string` prop and a **Default** button as the first child of `about-model__footer-actions` (before Cancel). Clicking it fills the draft so every swappable stage in that modal = `recommendedModel` (this makes the draft dirty; the user then presses Apply). Style it with the existing ghost button class.

- [ ] **Step 1: QAModeModal** — add `recommendedModel: string` to props. Add handler + button:

```tsx
  const setDefaults = () =>
    setDraft((prev) => ({ ...prev, scope: recommendedModel, generate: recommendedModel, verify: recommendedModel }));
```

In the footer actions, before Cancel:

```tsx
            <button type="button" className="about-model__btn about-model__btn--ghost" onClick={setDefaults}>Default</button>
```

- [ ] **Step 2: ChapterFacilitateModal + ChapterResumeModal** — add `recommendedModel: string` prop. Handler sets the chapter stages:

```tsx
  const setDefaults = () =>
    setDraft((prev) => ({
      ...prev,
      parse: recommendedModel, resolve: recommendedModel, map: recommendedModel,
      stitch: recommendedModel, ground: recommendedModel,
    }));
```

Add the same `Default` ghost button before Cancel in each footer.

- [ ] **Step 3: AboutModelModal (tutor)** — add `recommendedModel: string` prop. Handler sets the tutor swappable stages (leave `draftDiversity` / `draftWorkflow` untouched):

```tsx
  const setDefaults = () =>
    setDraftStageModels((prev) => ({
      ...prev,
      expansion: recommendedModel, image_judge: recommendedModel, plan: recommendedModel,
      draft: recommendedModel, vision_explain: recommendedModel,
    }));
```

Add the `Default` ghost button before Cancel in the tutor footer.

- [ ] **Step 4: App.tsx** — pass `recommendedModel={recommendedModel}` to all four modals (`AboutModelModal`, `QAModeModal`, `ChapterFacilitateModal`, `ChapterResumeModal`).

- [ ] **Step 5: Verify.**

Run: `cd web && npx tsc --noEmit && npx vitest run && npm run build` → clean; all tests pass; build succeeds.

- [ ] **Step 6: Commit.**

```bash
git add web/src/components/modals/AboutModelModal.tsx web/src/components/modals/QAModeModal.tsx web/src/components/modals/ChapterFacilitateModal.tsx web/src/components/modals/ChapterResumeModal.tsx web/src/App.tsx
git commit -m "feat(web): Default button in all mode modals — set stages to recommended model

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Browser verification on :5175

- [ ] Open each mode's `(i)` modal. Confirm a **Default** button sits next to Apply. Click it → every swappable stage's dropdown switches to **Qwen Plus**, footer flips to "Unsaved pipeline changes", Apply enables; press Apply → persists. Open a dropdown and confirm Qwen Plus shows a **★** recommended badge. Confirm the chatbox model picker also shows the ★ on Qwen Plus. No console errors.

---

## Self-review notes

- **Single source of truth:** `recommended` flag on the registry Model → `/api/models` → frontend badge + Default button (via `recommendedModelId(providers)`). The static `RECOMMENDED_MODEL_ID` is only the compile-time default for `activeModel`; it must equal the flagged id (qwen-plus) — noted in the file comment.
- **Backend default unchanged:** `ChatRequest.model` stays `gpt-5.4-nano` as the API-side fallback; the user-facing default is the picker (`activeModel` → qwen-plus), and the tutor `draft` node follows the picker (`__active__`).
- **Scope:** Default button sets only model stages (not tutor's diversity/workflow choice nodes), per the decision.
- **Types:** `recommendedModel: string` prop added uniformly; `setDraft`/`setDraftStageModels` are the existing draft setters in each modal.
