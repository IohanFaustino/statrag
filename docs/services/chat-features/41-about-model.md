# 41 — About-model modal + per-stage model routing

Date: 2026-05-20.

## What it does

The **Tutor card** in the Mode picker (open `Mode:` → the SWITCH MODE grid)
carries an `(i)` info button. Clicking it opens a modal **about Tutor mode**
(what it is, what it's designed for, its features — `data/tutorMode.ts`), NOT
about the chat model:

1. **Description (prose) + Features (bullet list)** describing the tutor mode.
   The modal has a pinned header (sticky, close always reachable), a scrolling
   body, section dividers, and a UI/UX modular type scale (18/14/13/12, 4-8px
   rhythm). The per-stage model selectors live in the diagram below.
2. **Tutor pipeline diagram** (input → output) — a **visual SVG graph**:
   node boxes connected by drawn curved edges + arrowheads, with the real
   parallel fork (concept-extraction ‖ retrieval → merge at rerank) then the
   linear tail. **Swappable** nodes carry a **custom dropdown** (`NodeModelDropdown`)
   that replicates the chatbox model picker — provider icons + models grouped
   by provider, floating (`position: fixed`) so it is never clipped — and
   re-routes that stage on the next query. **Locked** nodes (embedding,
   reranker, vision) are shown but fixed. Layout is hand-laid in
   `PipelineDiagram.tsx` (`LAYOUT` map, 520×768 coordinate space).

The modal is sized to sit **between the side menus** (`fm__panel--about`,
`width: min(100%, 880px)`), not full screen, with a UI/UX-tuned type scale.

## Iteration history (what was wrong before)

This feature took several corrective passes; recording the misreads so they
are not repeated:

1. **`(i)` placement (twice wrong).** First put inside each *row of the model
   dropdown* (hover-only, `opacity: 0` → invisible). Then moved to the *model
   selector card* in the toolbar. The actual requirement was the **Tutor card**
   in the Mode-switcher grid. Now correct.
2. **Diagram was a vertical list**, not a diagram. Rebuilt as a real **SVG
   graph** (boxes + drawn edges, parallel fork).
3. **Node model picker was a native `<select>`.** Replaced with a custom
   dropdown that visually matches the chatbox model picker (provider icons +
   grouped models).
4. **Capabilities were a card grid.** Changed to a **bullet list + prose**.
5. **Modal was near full-screen** (`fm__panel--lg`, 1600px). Constrained to
   `fm__panel--about` (880px), centered between the menus.
6. **Font sizes were oversized/inconsistent.** Applied a UI/UX type scale
   (title 17 / blurb 13 / sub 12 caps / body 14.5 @1.55 / bullets 14 @1.5).
7. **Node dropdown displaced** (opened far from its toggle). Cause: the modal
   `.fm__panel` uses `backdrop-filter`, which (like `transform`) makes it the
   containing block for `position: fixed`, so the panel anchored to the modal
   not the viewport. Fix: `NodeModelDropdown` renders its panel via
   `createPortal(…, document.body)` to escape both the containing block and
   the panel's `overflow: hidden`.
8. **Modal described the model, not the mode.** Since the `(i)` lives on the
   Tutor card, the modal now describes **Tutor mode** (`data/tutorMode.ts`):
   what it is, what it's for, its features. Removed the redundant "click a
   swappable stage…" hint. Applied a UI/UX polish pass (sticky header,
   scrolling body, modular type scale, section dividers, node icons in the
   project accent instead of brand colors; dropdown panel solid `#000`, active
   row red).

## Why the backend changed

The model picker was **cosmetic**: `run_deep_tutor` hardwired every LLM call
to `settings.openai_model_nano` and only echoed `req.model` in metadata. To
make per-stage overrides real, a `model` param was threaded through
`extract_concepts`, `_stream_draft`, `critique`, and `judge_image_candidates`.

- **draft** now honors the selected model. OpenAI models use the native
  structured-streaming path; non-OpenAI (deepseek) use a best-effort
  text-stream + JSON-parse path (`_stream_draft_via_router`) — may be slower
  or less strictly structured.
- **expansion / critique / image_judge** default to nano (cheap) and only
  change when explicitly overridden with a valid picker model.

## Contracts

| Concern | Where |
|---|---|
| Request field | `ChatRequest.stageModels: dict[str,str] \| None` |
| Overridable stages | `_OVERRIDABLE_STAGES = {expansion, draft, critique, image_judge}` |
| Resolver | `_resolve_stage_model(stage, default_model, stage_models)` |
| Validation | unknown stage/model → stage default (no error) |
| Integrity | embedding / rerank / vision never read `stageModels` |
| FE data | `web/src/data/modelMeta.ts`, `web/src/data/tutorPipeline.ts` |
| FE components | `modals/AboutModelModal.tsx`, `PipelineDiagram.tsx`, `NodeModelDropdown.tsx`, `(i)` on Tutor card in `ModePicker.tsx`, `panelClassName` prop in `modals/FocusModal.tsx` |

## Tests (5 categories)

- **performance** — diagram/modal render are pure (renderToStaticMarkup);
  resolver is O(stages); backend adds no extra LLM calls.
- **reliability** — `test_request_back_compat_no_stage_models`,
  `test_unknown_model_ignored_falls_back`, `test_garbage_stage_key_ignored`.
- **integrity** — `test_non_overridable_stages_never_rerouted`,
  `test_draft_default_is_picker_model_others_nano`.
- **usability** — `PipelineDiagram.test.tsx` (selects for swappable, fixed for
  locked, modal open/closed); live Chrome check of `(i)` → modal → swap.
- **relevance** — `test_valid_override_reaches_draft_stage` (override is the
  model actually passed to `_stream_draft`).

## Limitations / follow-ups

- DeepSeek draft is best-effort (no native schema streaming); quality/latency
  may differ from OpenAI.
- Diagram covers **tutor mode** only; other modes' pipelines not yet drawn.
- Overrides are session state (not persisted per conversation).


---

**2026-05-20 update — model dropdown flip-up + internal scroll**

`NodeModelDropdown` now flips upward when space below the trigger is insufficient and clamps max-height (≤320px) with internal `overflow-y:auto`, so the full provider list is reachable for low pipeline stages. See changelog 2026-05-20 §3.


**2026-05-21 update — vision model selectable**

The Vision explain stage is now a non-locked pipeline node with its own SWAP dropdown. Override flows via `stageModels["vision_explain"]` → `deep_tutor._resolve_vision_model` → vision call. Default stays gpt-4o-mini; non-vision picks fall back to the caption. See changelog 2026-05-21.
