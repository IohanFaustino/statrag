# Remove non-tutor chat modes — design

**Date:** 2026-05-31
**Branch:** `feat/remove-nontutor-modes` (off `main`)
**Status:** approved (design)

## Goal

Remove the 10 non-tutor chat modes from every layer (backend, frontend, docs),
leaving the **tutor** experience 100% intact. Modes will be re-built
incrementally later; the original 10 are abandoned.

Modes removed: `compare`, `figures`, `quiz`, `navigate`, `prereqs`,
`annotate`, `research`, `math`, `path`, `roadmap`.

Mode kept: `tutor` (the deep-tutor pipeline + its v1/v2 fallbacks).

## Scope decisions

1. **Surgical, not collapse.** Tutor's full plumbing stays untouched —
   `deep_tutor` pipeline, v1 `orchestrator.py` tutor path, `mode_impls/tutor.py`,
   the `tutor` registration in `modes.py`, `use_v2_modes` flag. Only artifacts
   dedicated to the other 10 modes are removed; in shared files only the
   10-mode branches/entries are excised.
2. **Keep the mode-selection scaffold.** The `mode` request field, the `ModeId`
   type, and the `ModePicker` UI are retained (tutor-only). Re-adding a mode
   later means registering it + adding its value back, not rebuilding plumbing.
3. **`ModeId = Literal["tutor"]`.** Collapse the value set to a single member.
   Type-safe: an unimplemented mode is rejected at the schema boundary instead
   of routing to a dead branch. Re-add a value per mode when built.

## Architecture

The chat dispatch chain that must keep working unchanged:

```
api.py  /api/chat
  → router.stream_chat(req)
      → _v2_enabled_for("tutor")?  (settings.use_v2_modes)
          yes → req.mode=="tutor" + TUTOR_DEEP_MODE!=0 → agents.deep_tutor.run_deep_tutor   [PRIMARY]
                req.mode=="tutor" + TUTOR_DEEP_MODE==0 → _tutor_v2 (mode_impls.tutor)        [fallback]
          no  → _v1_passthrough → orchestrator.stream_chat → ModeRegistry.get("tutor")       [fallback]
```

Everything else in that chain (the `_structured_v2`, `_multi_agent_v2`, and the
prereqs/research/path/figures/math branches) is removed.

## Components & changes

### Backend — whole-file deletes
- `src/services/chat/prompts/`: `annotate.py`, `compare.py`, `figures.py`,
  `math.py`, `navigate.py`, `path.py`, `prereqs.py`, `quiz.py`, `research.py`,
  `roadmap.py`. Keep `deep_tutor.py`, `tutor.py`, `__init__.py`.
- `src/services/chat/mode_impls/`: `compare.py`, `figures.py`, `math.py`,
  `navigate.py`, `quiz.py`, `roadmap.py`, `annotate.py`. Keep `tutor.py`,
  `_common.py`, `__init__.py`.
- `src/services/chat/agents/`: `prereqs.py`, `prereqs_lg.py`, `research.py`,
  `research_lg.py`, `study_path.py`, `study_path_lg.py`, `graph.py`, `nodes.py`,
  `state.py`. Keep `deep_tutor.py`, `orchestrator_workers.py`, `coverage.py`,
  `image_judge.py`, `__init__.py`.
  - **Verify before delete:** confirm `graph.py`/`nodes.py`/`state.py` are used
    only by the removed multi-agent modes (prereqs/research/path). `deep_tutor`
    imports only `coverage`, `image_judge`, `orchestrator_workers` — if any of
    graph/nodes/state is also imported by a kept file, retain it.
- `src/services/chat/tests/`: `test_agents_prereqs.py`,
  `test_agents_research.py`, `test_agents_study_path.py`, `test_modes.py`
  (rewrite to tutor-only if it asserts the 11-mode registry),
  `test_t10_structured_modes.py`, `test_t11_multi_agent_lg.py`,
  `test_t07_graph_retry.py`, `test_agents_graph.py`.
  - **Verify before delete:** keep any test that also covers tutor/shared infra.

### Backend — surgical edits (shared files)
- `schemas/_core.py`: `ModeId = Literal["tutor"]`. Keep the `mode` field and its
  `"tutor"` default on `ChatRequest` / `ConversationDigest`.
- `schemas/output.py`: delete the 10 mode output classes and their helper
  submodels that nothing else imports — `CompareAnswer`, `BookSection`,
  `FiguresAnswer`, `Question`, `Quiz`, `NavResult`, `NavigationList`,
  `ConceptNode`, `ConceptEdge`, `DAG`, `Annotation`, `AnnotatedReading`,
  `StanceClaim`, `Report`, `MathAnswer`, `StudyWeek`, `StudyPlan`, `Scene`,
  `Roadmap`. Keep `Citation`, `FigureRef`, `TutorCitation`, `TutorAnswer`,
  `DeepTutorAnswer`, `AuthorContrast`, `WorkerTask`, `OrchestratorPlan`,
  `AuthorBrief`, `SynthesisPlan`.
  - **Verify before delete:** grep each class name across `src/` and `web/`;
    only delete if no kept file imports it.
- `modes.py`: `register_all_modes` keeps only the `tutor` block; remove the
  other 10 registrations and their prompt/schema imports.
- `router.py`: remove `_STRUCTURED_V2_MODES`, `_structured_v2`,
  `_multi_agent_v2`, and the `{"prereqs","research","path"}` branch in
  `stream_chat`. Keep the tutor branch (deep + v2 fallback) and `_v1_passthrough`.
- `orchestrator.py`: remove the `arch=="multi"` prereqs/research/path branches
  and the figures/math vision-mode branch. Keep the tutor flow
  (`spec.id=="tutor"` → `build_tutor_prompt`).
- `api.py`: remove the study-plan (Mode 10 `path`) endpoints (~L273-399) and the
  `_ReplanBody` model.
- `core/config.py`: set `use_v2_modes` default so tutor is v2-enabled; drop any
  now-irrelevant per-mode entries. Do not remove the flag (tutor uses it).

### Frontend — whole-file deletes
- `web/src/components/views/`: `AnnotateView.tsx`, `DAGView.tsx`,
  `NavigationView.tsx`, `QuizView.tsx`, `ReportView.tsx`, `RoadmapView.tsx`,
  `StudyPathView.tsx` (+ any co-located `.test.tsx`). Keep `TutorView.tsx` and
  its tests, `normalizeMathDelimiters.test.ts`.

### Frontend — surgical edits
- `types.ts`: `ModeId = "tutor"`. Remove dead structured types (`Quiz`,
  `AnnotatedReading`, `Roadmap`, `NavigationList`, `DAG`, `StudyPlan`,
  `MathAnswer`, `FiguresAnswer`, `Report`, …) and their `structured_output`
  union variants. Keep tutor + figure types.
- `App.tsx`: `STATRAG_MODES` → single `{ id:"tutor", label:"Tutor", glyph:"T" }`.
- `MessageThread.tsx`: `STRUCTURED_MODES` → tutor-relevant set; trim the
  structured-renderer switch and `MODE_ICONS`/`MODE_LABELS` to tutor.
- `ModePicker.tsx`: `MODE_ICON_MAP` → tutor only. Keep the component.
- `Icons.tsx`: remove now-unused icon exports (verify no other importers).
- `lib/exportStructured.ts` (+ `.test.ts`): drop per-mode export branches.
- `InputBar.tsx`, `Sidebar.tsx`: trim mode-list props/usages to tutor.

### Docs
- Delete `docs/services/modes/{annotate,compare,figures,math,navigate,path,prereqs,quiz,research,roadmap}.md`.
  Keep `tutor.md`; rewrite `docs/services/modes/README.md` to list tutor only.
- Update references in `docs/services/chat.md`, `docs/services/frontend.md`,
  `docs/services/retrieval.md`, `docs/system/architecture.md`,
  `docs/system/invariants.md`, `docs/system/changelog.md` (add a removal entry),
  and `CLAUDE.md` (any mode-count mentions).

### Out of scope (no change)
- `scripts/draft_battle.py` — tutor-only, no mode dependency.
- The deep-tutor pipeline stages, prompts, schemas, modal card
  (`tutorPipeline.ts`/`PipelineDiagram.tsx`), and their docs/tests.

## Data flow / error handling
- A request with any non-tutor `mode` value now fails Pydantic validation at the
  API boundary (422) instead of reaching a removed branch. Acceptable: the
  frontend only ever sends `tutor`.
- No DB/migration impact. Study-plan persistence (`store.upsert_study_plan`) is
  orphaned once `path` endpoints go; remove the store helper only if nothing
  else calls it (verify), else leave dormant.

## Testing / verification
1. Backend import smoke: `python -c "import src.services.chat.api"` clean.
2. `pytest src/services/chat/tests` green (after trimming mode tests).
3. `cd web && npm run build` (tsc) clean; `npx vitest run` green.
4. Browser :5175 via `./scripts/dev.sh`: ModePicker shows only **Tutor**; send a
   tutor question, confirm streaming + citations + structured tutor view render;
   open the tutor (i) modal and confirm the pipeline diagram is unchanged.
5. `grep -rn` sweep for each removed mode id across `src/` and `web/` returns no
   live references (only historical changelog mentions allowed).

## Execution order (low-risk first)
1. Frontend: shrink `STATRAG_MODES` to tutor (UI immediately tutor-only).
2. Backend dispatch: trim `router.py` + `orchestrator.py` branches; remove
   `api.py` path endpoints.
3. Delete dedicated backend files (prompts, mode_impls, agents) + trim `modes.py`,
   `schemas`.
4. Delete frontend view files + trim `types.ts`, `MessageThread.tsx`, exports.
5. Docs + changelog.
6. Full verification sweep.

Each step: edit → build/import check → commit.
