# Remove Non-Tutor Chat Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the 10 non-tutor chat modes (compare, figures, quiz, navigate, prereqs, annotate, research, math, path, roadmap) from backend, frontend, and docs while leaving the tutor experience 100% intact.

**Architecture:** Surgical removal. Delete files dedicated to the 10 modes; in shared files excise only the 10-mode branches/entries. Tutor plumbing (deep_tutor pipeline, v1 orchestrator tutor path, mode_impls/tutor.py, modes.py tutor registration, use_v2_modes flag) is untouched. The mode-selection scaffold (mode field, ModeId type, ModePicker UI) is kept, tutor-only. `ModeId` collapses to `Literal["tutor"]`.

**Tech Stack:** Python 3.12 (FastAPI, Pydantic, LangChain/LangGraph), TypeScript + React/Vite, vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-05-31-remove-nontutor-modes-design.md`

**Branch:** `feat/remove-nontutor-modes` (already created off main).

**Note on TDD:** This is a removal task — most "tests" are verification gates (grep sweeps, import smoke, build, existing test suite). Each task ends with a concrete verification command + expected output, then a commit. The guiding invariant for every task: **tutor must keep working** — `python -c "import src.services.chat.api"` must stay clean and the tutor browser flow unbroken.

---

## Task 0: Dependency verification (read-only, no commit)

Confirm the "verify before delete" assumptions in the spec before any deletion. Record findings; if any assumption is false, STOP and report.

**Files:** none modified.

- [ ] **Step 1: Confirm deep_tutor agent imports**

Run:
```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
grep -n "from src.services.chat.agents" src/services/chat/agents/deep_tutor.py
```
Expected: imports ONLY from `coverage`, `image_judge`, `orchestrator_workers`. If it imports `graph`, `nodes`, or `state`, those files must be KEPT — note it.

- [ ] **Step 2: Confirm graph/nodes/state are multi-agent-only**

Run:
```bash
grep -rln "agents.graph\|agents.nodes\|agents.state\b" src/services/chat --include=*.py | grep -v __pycache__ | grep -v tests/
```
Expected: only `orchestrator.py`, `router.py`, `agents/prereqs*.py`, `agents/research*.py`, `agents/study_path*.py` (all being removed/trimmed). If a KEPT file (deep_tutor, orchestrator_workers, coverage, image_judge, tutor) references them, note it.

- [ ] **Step 3: Confirm shared-schema usage**

Run:
```bash
for c in CompareAnswer FiguresAnswer Quiz NavigationList DAG AnnotatedReading Report MathAnswer StudyPlan Roadmap BookSection Question NavResult ConceptNode ConceptEdge Annotation StanceClaim StudyWeek Scene; do echo "== $c =="; grep -rln "\b$c\b" src/ web/ --include=*.py --include=*.ts --include=*.tsx | grep -v __pycache__ | grep -v node_modules; done
```
Expected: each appears only in files slated for deletion/trim (output.py, modes.py, orchestrator.py, the removed mode_impls/agents, types.ts, the removed views, exportStructured, MessageThread). If any kept file references one, note it (do NOT delete that class).

- [ ] **Step 4: Confirm store study-plan helper usage**

Run:
```bash
grep -rn "upsert_study_plan\|get_study_plan\|study_plan" src/services/chat --include=*.py | grep -v __pycache__ | grep -v tests/
```
Expected: only `api.py` (path endpoints, being removed) and `store.py` (definition). If only api.py uses it, the store helper can be removed in Task 6; else leave dormant.

- [ ] **Step 5: Report findings**

Write a short summary of any assumption that proved false. If all hold, proceed. No commit (read-only task).

---

## Task 1: Frontend — shrink mode list to tutor-only

Make the UI tutor-only first (immediate visible effect, lowest risk).

**Files:**
- Modify: `web/src/App.tsx` (`STATRAG_MODES`)

- [ ] **Step 1: Edit STATRAG_MODES**

In `web/src/App.tsx`, replace the `STATRAG_MODES` array with a single entry:
```ts
const STATRAG_MODES: ModeMeta[] = [
  { id: "tutor", label: "Tutor", glyph: "T" },
];
```

- [ ] **Step 2: Verify build**

Run:
```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG/web && npm run build 2>&1 | tail -20
```
Expected: build succeeds (no TS errors). `ModeId` still allows the other strings at this point, so no type break yet.

- [ ] **Step 3: Commit**

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
git add web/src/App.tsx
git commit -m "feat(chat): show only Tutor in mode picker"
```

---

## Task 2: Backend — trim router dispatch to tutor-only

**Files:**
- Modify: `src/services/chat/router.py`

- [ ] **Step 1: Remove non-tutor dispatch branches**

In `src/services/chat/router.py`:
- Delete the `_STRUCTURED_V2_MODES` dict.
- Delete the `_structured_v2` function.
- Delete the `_multi_agent_v2` function.
- In `stream_chat`, delete the `if req.mode in _STRUCTURED_V2_MODES:` block and the `if req.mode in {"prereqs", "research", "path"}:` block.

Keep: `_v2_enabled_for`, `_v1_passthrough`, `_tutor_v2`, and the `if req.mode == "tutor":` branch (deep_tutor + v2 fallback). Keep the final `_v1_passthrough` fallthrough.

- [ ] **Step 2: Verify import**

Run:
```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
python -c "import src.services.chat.router" && echo OK
```
Expected: `OK` (no ImportError from deleted helpers).

- [ ] **Step 3: Commit**

```bash
git add src/services/chat/router.py
git commit -m "refactor(chat): drop non-tutor dispatch branches from router"
```

---

## Task 3: Backend — trim v1 orchestrator to tutor flow

**Files:**
- Modify: `src/services/chat/orchestrator.py`

- [ ] **Step 1: Remove multi-agent + vision-mode branches**

In `src/services/chat/orchestrator.py`:
- Delete the `if spec.arch == "multi" and req.mode == "prereqs":` block.
- Delete the `if spec.arch == "multi" and req.mode == "research":` block.
- Delete the `if spec.arch == "multi" and req.mode == "path":` block.
- Delete the figures/math vision-mode handling: the `_is_vision_mode = spec.model == "pro_vision" and req.mode in ("figures", "math")` logic and its dependent figure-emit branch (the `if _is_vision_mode:` block and the "per-figure events (vision modes only)" block).
- Remove now-unused imports of `agents.prereqs`, `agents.research`, `agents.study_path` (and any lazy imports inside the deleted blocks).

Keep: `ModeRegistry` import + `ModeRegistry.get(req.mode)` fallback-to-tutor, the `if spec.id == "tutor": system_text = build_tutor_prompt(sources)` flow, the generic retrieve flow, and the `_repair_structured_output` helper (used by tutor's TutorAnswer).

- [ ] **Step 2: Verify import**

Run:
```bash
python -c "import src.services.chat.orchestrator" && echo OK
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add src/services/chat/orchestrator.py
git commit -m "refactor(chat): reduce v1 orchestrator to tutor flow"
```

---

## Task 4: Backend — remove study-plan (path) API endpoints

**Files:**
- Modify: `src/services/chat/api.py`
- Modify (conditional): `src/services/chat/store.py` (only if Task 0 Step 4 found api.py is the sole caller)

- [ ] **Step 1: Remove path endpoints**

In `src/services/chat/api.py`, delete the "Study plan endpoints (Mode 10)" section: the `_ReplanBody` model and both study-plan route handlers (~L273-399). Remove any now-unused imports they relied on (e.g. study_path agent, StudyPlan schema).

- [ ] **Step 2: (Conditional) remove orphaned store helper**

If Task 0 Step 4 confirmed only api.py called `upsert_study_plan`/study-plan helpers, delete those functions from `src/services/chat/store.py`. Otherwise skip.

- [ ] **Step 3: Verify import**

Run:
```bash
python -c "import src.services.chat.api" && echo OK
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add src/services/chat/api.py src/services/chat/store.py
git commit -m "refactor(chat): remove study-plan (path mode) endpoints"
```

---

## Task 5: Backend — collapse ModeId and trim output schemas

**Files:**
- Modify: `src/services/chat/schemas/_core.py`
- Modify: `src/services/chat/schemas/output.py`
- Modify: `src/services/chat/schemas/__init__.py` (if it re-exports removed classes)

- [ ] **Step 1: Collapse ModeId**

In `src/services/chat/schemas/_core.py`, replace:
```python
ModeId = Literal[
    "tutor", "compare", "figures", "quiz", "navigate",
    "prereqs", "annotate", "research", "math", "path", "roadmap",
]
```
with:
```python
ModeId = Literal["tutor"]
```
Leave the `mode: ModeId = "tutor"` fields and `ProviderId` unchanged.

- [ ] **Step 2: Delete dead output classes**

In `src/services/chat/schemas/output.py`, delete these classes (only those confirmed unused in Task 0 Step 3): `CompareAnswer`, `BookSection`, `FiguresAnswer`, `Question`, `Quiz`, `NavResult`, `NavigationList`, `ConceptNode`, `ConceptEdge`, `DAG`, `Annotation`, `AnnotatedReading`, `StanceClaim`, `Report`, `MathAnswer`, `StudyWeek`, `StudyPlan`, `Scene`, `Roadmap`.

Keep: `Citation`, `FigureRef`, `TutorCitation`, `TutorAnswer`, `DeepTutorAnswer`, `AuthorContrast`, `WorkerTask`, `OrchestratorPlan`, `AuthorBrief`, `SynthesisPlan`.

- [ ] **Step 3: Fix __init__ re-exports**

In `src/services/chat/schemas/__init__.py`, remove any imports/`__all__` entries for the deleted classes.

- [ ] **Step 4: Verify import**

Run:
```bash
python -c "import src.services.chat.schemas; import src.services.chat.schemas.output" && echo OK
```
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/schemas/
git commit -m "refactor(chat): ModeId=tutor only; drop non-tutor output schemas"
```

---

## Task 6: Backend — trim modes.py registry to tutor

**Files:**
- Modify: `src/services/chat/modes.py`

- [ ] **Step 1: Trim register_all_modes and imports**

In `src/services/chat/modes.py`:
- In `register_all_modes`, keep only the `tutor` `ModeRegistry.register(...)` block; delete the other 10.
- Trim the `from src.services.chat.prompts import (...)` block inside the function to import only `tutor as tutor_p`.
- Trim the top-of-file `from src.services.chat.schemas.output import (...)` to import only `TutorAnswer`.
- Update the module docstring ("All 11 modes" → "tutor mode") and the `register_all_modes` docstring.

- [ ] **Step 2: Verify import + registry**

Run:
```bash
python -c "from src.services.chat.modes import ModeRegistry; print([m.id for m in ModeRegistry.all()])"
```
Expected: `['tutor']`.

- [ ] **Step 3: Commit**

```bash
git add src/services/chat/modes.py
git commit -m "refactor(chat): tutor-only mode registry"
```

---

## Task 7: Backend — delete dedicated mode files (prompts, mode_impls, agents)

**Files:**
- Delete (prompts): `annotate.py`, `compare.py`, `figures.py`, `math.py`, `navigate.py`, `path.py`, `prereqs.py`, `quiz.py`, `research.py`, `roadmap.py`
- Delete (mode_impls): `compare.py`, `figures.py`, `math.py`, `navigate.py`, `quiz.py`, `roadmap.py`, `annotate.py`
- Delete (agents): `prereqs.py`, `prereqs_lg.py`, `research.py`, `research_lg.py`, `study_path.py`, `study_path_lg.py`, `graph.py`, `nodes.py`, `state.py` — **EXCEPT any flagged KEEP in Task 0 Steps 1-2.**

- [ ] **Step 1: Delete prompt files**

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
git rm src/services/chat/prompts/{annotate,compare,figures,math,navigate,path,prereqs,quiz,research,roadmap}.py
```

- [ ] **Step 2: Delete mode_impls files**

```bash
git rm src/services/chat/mode_impls/{compare,figures,math,navigate,quiz,roadmap,annotate}.py
```

- [ ] **Step 3: Delete agent files (honor Task 0 KEEP flags)**

```bash
git rm src/services/chat/agents/{prereqs,prereqs_lg,research,research_lg,study_path,study_path_lg,graph,nodes,state}.py
```
If Task 0 flagged graph/nodes/state as needed by a kept file, omit those from this command.

- [ ] **Step 4: Check for dangling imports of deleted modules**

Run:
```bash
grep -rn "prompts.annotate\|prompts.compare\|prompts.figures\|prompts.math\|prompts.navigate\|prompts.path\|prompts.prereqs\|prompts.quiz\|prompts.research\|prompts.roadmap\|mode_impls.compare\|mode_impls.figures\|mode_impls.math\|mode_impls.navigate\|mode_impls.quiz\|mode_impls.roadmap\|mode_impls.annotate\|agents.prereqs\|agents.research\|agents.study_path\|agents.graph\|agents.nodes\|agents.state" src/services/chat --include=*.py | grep -v __pycache__ | grep -v "/tests/"
```
Expected: no output. If any line appears in a non-test file, fix that reference (it should have been removed in Tasks 2-6).

- [ ] **Step 5: Verify full backend import**

Run:
```bash
python -c "import src.services.chat.api" && echo OK
```
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add -A src/services/chat/prompts src/services/chat/mode_impls src/services/chat/agents
git commit -m "refactor(chat): delete dedicated non-tutor mode files"
```

---

## Task 8: Backend — trim/delete mode tests

**Files:**
- Delete: `tests/test_agents_prereqs.py`, `test_agents_research.py`, `test_agents_study_path.py`, `test_t10_structured_modes.py`, `test_t11_multi_agent_lg.py`, `test_t07_graph_retry.py`, `test_agents_graph.py`
- Modify or delete: `tests/test_modes.py`, `test_stage_models.py` (only if they assert removed modes)

- [ ] **Step 1: Inspect mode-coupled tests**

Run:
```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
grep -ln "compare\|figures\|quiz\|navigate\|prereqs\|annotate\|research\|\"math\"\|\"path\"\|roadmap\|11 mode\|ModeRegistry" src/services/chat/tests/test_modes.py src/services/chat/tests/test_stage_models.py
```
Read each flagged test. If it asserts the 11-mode registry / removed modes, plan to trim those assertions to tutor-only or delete the file if it is entirely about removed modes.

- [ ] **Step 2: Delete fully-obsolete test files**

```bash
git rm src/services/chat/tests/{test_agents_prereqs,test_agents_research,test_agents_study_path,test_t10_structured_modes,test_t11_multi_agent_lg,test_t07_graph_retry,test_agents_graph}.py
```

- [ ] **Step 3: Trim partially-coupled tests**

Edit `test_modes.py` (and `test_stage_models.py` if needed): remove assertions referencing removed modes; keep tutor assertions. If a file is entirely removed-mode coverage, `git rm` it instead.

- [ ] **Step 4: Run backend test suite**

Run:
```bash
.venv/bin/python -m pytest src/services/chat/tests -q 2>&1 | tail -25
```
Expected: all collected tests pass; no import errors from deleted modules.

- [ ] **Step 5: Commit**

```bash
git add -A src/services/chat/tests
git commit -m "test(chat): remove non-tutor mode tests"
```

---

## Task 9: Frontend — delete mode view components

**Files:**
- Delete: `web/src/components/views/{AnnotateView,DAGView,NavigationView,QuizView,ReportView,RoadmapView,StudyPathView}.tsx` and any co-located `.test.tsx`.

- [ ] **Step 1: Delete view files**

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
git rm web/src/components/views/{AnnotateView,DAGView,NavigationView,QuizView,ReportView,RoadmapView,StudyPathView}.tsx
```
(Keep `TutorView.tsx`, its `.test.tsx` files, and `normalizeMathDelimiters.test.ts`.)

- [ ] **Step 2: Find importers of deleted views**

Run:
```bash
grep -rn "AnnotateView\|DAGView\|NavigationView\|QuizView\|ReportView\|RoadmapView\|StudyPathView" web/src --include=*.ts --include=*.tsx | grep -v node_modules
```
Expected after Task 10: no output. For now, note importers (likely `MessageThread.tsx`) — they're fixed in Task 10.

- [ ] **Step 3: Commit**

```bash
git add -A web/src/components/views
git commit -m "feat(chat): delete non-tutor view components"
```

---

## Task 10: Frontend — trim types, renderers, picker, exports

**Files:**
- Modify: `web/src/types.ts`
- Modify: `web/src/components/MessageThread.tsx`
- Modify: `web/src/components/ModePicker.tsx`
- Modify: `web/src/components/Icons.tsx`
- Modify: `web/src/lib/exportStructured.ts` (+ `exportStructured.test.ts`)
- Modify (if needed): `web/src/components/InputBar.tsx`, `web/src/components/Sidebar.tsx`

- [ ] **Step 1: Collapse ModeId + drop dead types in types.ts**

In `web/src/types.ts`:
- `export type ModeId = "tutor";`
- Delete interfaces/types only used by removed modes: `Quiz`, `Question`, `AnnotatedReading`, `Annotation`, `Roadmap`, `Scene`, `NavigationList`, `NavResult`, `DAG`, `ConceptNode`, `ConceptEdge`, `StudyPlan`, `StudyWeek`, `MathAnswer`, `FiguresAnswer`, `BookSection`, `CompareAnswer`, `Report`, `StanceClaim` (whichever exist).
- In the `structured_output` discriminated union, remove the variants for removed schemas (`"Quiz"`, `"AnnotatedReading"`, `"Roadmap"`, `"NavigationList"`, `"DAG"`, `"StudyPlan"`, `"MathAnswer"`, `"CompareAnswer"`, `"FiguresAnswer"`, `"Report"`). Keep tutor + figures-stream variants used by deep_tutor.
- Keep `figures`/`Figure`/`FigureRef` types (deep_tutor uses figures).

- [ ] **Step 2: Trim MessageThread.tsx**

In `web/src/components/MessageThread.tsx`:
- `STRUCTURED_MODES` → `new Set(["tutor"])` (or remove the gate if it only guarded removed modes — keep tutor JSON-hiding behavior intact).
- Remove imports of deleted view components and their branches in the structured-output render switch. Keep the `TutorView` branch.
- Trim `MODE_ICONS` / `MODE_LABELS` maps to the `tutor` entry.

- [ ] **Step 3: Trim ModePicker.tsx**

In `web/src/components/ModePicker.tsx`, reduce `MODE_ICON_MAP` to `{ tutor: IconBook }`. Keep the component and its props.

- [ ] **Step 4: Trim Icons.tsx**

In `web/src/components/Icons.tsx`, remove icon exports no longer imported anywhere. First confirm each is unused:
```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
for i in IconCompare IconImage IconQuiz IconSearch IconTree IconPen IconFlask IconMath IconCal IconFilm; do echo "== $i =="; grep -rln "$i" web/src --include=*.tsx --include=*.ts | grep -v Icons.tsx | grep -v node_modules; done
```
Delete only icons with no remaining importer. (Some — e.g. IconSearch — may be used elsewhere; keep those.)

- [ ] **Step 5: Trim exportStructured.ts**

In `web/src/lib/exportStructured.ts`, remove per-mode export branches for removed schemas; keep the tutor branch. Update `exportStructured.test.ts` to drop cases for removed modes.

- [ ] **Step 6: Trim InputBar/Sidebar if needed**

If `InputBar.tsx` or `Sidebar.tsx` enumerate modes beyond the `modes` prop, trim to tutor. (The `modes` prop already flows from the shrunk `STATRAG_MODES`.)

- [ ] **Step 7: Verify build + tests**

Run:
```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG/web
npm run build 2>&1 | tail -20 && npx vitest run 2>&1 | tail -25
```
Expected: tsc build clean (no unused/import errors), vitest green.

- [ ] **Step 8: Commit**

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
git add -A web/src
git commit -m "feat(chat): tutor-only types, renderers, picker, exports"
```

---

## Task 11: Docs — remove mode docs and update references

**Files:**
- Delete: `docs/services/modes/{annotate,compare,figures,math,navigate,path,prereqs,quiz,research,roadmap}.md`
- Modify: `docs/services/modes/README.md`, `docs/services/chat.md`, `docs/services/frontend.md`, `docs/services/retrieval.md`, `docs/system/architecture.md`, `docs/system/invariants.md`, `docs/system/changelog.md`, `CLAUDE.md`

- [ ] **Step 1: Delete per-mode docs**

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
git rm docs/services/modes/{annotate,compare,figures,math,navigate,path,prereqs,quiz,research,roadmap}.md
```

- [ ] **Step 2: Rewrite modes README**

Edit `docs/services/modes/README.md` to list only `tutor`, with a one-line note: "The original 10 non-tutor modes were removed on 2026-05-31 (see changelog); modes will be re-introduced incrementally."

- [ ] **Step 3: Update cross-references**

Grep and fix mode mentions:
```bash
grep -rln "compare\|figures\|quiz\|navigate\|prereqs\|annotate\|research\|roadmap\|11 mode\|Mode 10\|study plan" docs/services/chat.md docs/services/frontend.md docs/services/retrieval.md docs/system/architecture.md docs/system/invariants.md CLAUDE.md
```
Edit each to reflect tutor-only (remove mode tables/lists, fix counts). Do not touch deep-tutor pipeline docs under `docs/services/chat-features/`.

- [ ] **Step 4: Add changelog entry**

Append to `docs/system/changelog.md` a dated entry: "2026-05-31 — Removed the 10 non-tutor chat modes (compare/figures/quiz/navigate/prereqs/annotate/research/math/path/roadmap) across backend, frontend, and docs. Tutor (deep-tutor pipeline) and the mode-selection scaffold retained; `ModeId` collapsed to `Literal['tutor']`. Spec: docs/superpowers/specs/2026-05-31-remove-nontutor-modes-design.md."

- [ ] **Step 5: Commit**

```bash
git add -A docs CLAUDE.md
git commit -m "docs(chat): remove non-tutor mode docs; update references"
```

---

## Task 12: Final verification sweep

**Files:** none modified (unless a leak is found).

- [ ] **Step 1: Live-reference sweep**

Run:
```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
grep -rn "\"compare\"\|\"figures\"\|\"quiz\"\|\"navigate\"\|\"prereqs\"\|\"annotate\"\|\"research\"\|\"roadmap\"\|'compare'\|'prereqs'" src/ web/src --include=*.py --include=*.ts --include=*.tsx | grep -v __pycache__ | grep -v node_modules | grep -v "\.test\."
```
Expected: no live references (matches in deleted files won't appear). Investigate any hit.

- [ ] **Step 2: Backend import + tests**

Run:
```bash
python -c "import src.services.chat.api" && echo OK
.venv/bin/python -m pytest src/services/chat/tests -q 2>&1 | tail -15
```
Expected: `OK`; tests green.

- [ ] **Step 3: Frontend build + tests**

Run:
```bash
cd web && npm run build 2>&1 | tail -10 && npx vitest run 2>&1 | tail -15
```
Expected: build clean; vitest green.

- [ ] **Step 4: Browser smoke on :5175**

Start `./scripts/dev.sh`. In the browser at :5175:
- ModePicker shows only **Tutor**.
- Send a tutor question (e.g. "explain bias-variance tradeoff"); confirm streaming answer, citation cards, and the structured tutor view render.
- Open the tutor (i) modal; confirm the pipeline diagram renders unchanged (matches `docs/common ground/index.html`).

Record the result. If anything is broken, STOP and report.

- [ ] **Step 5: (If clean) no commit needed**

Verification only. The branch is ready for `superpowers:finishing-a-development-branch`.

---

## Done criteria

- `ModeId == Literal["tutor"]` (backend + frontend).
- All 10 modes' dedicated files (prompts, mode_impls, agents, views, docs, tests) deleted.
- Shared files contain no live non-tutor branches.
- Tutor browser flow works; pipeline modal unchanged.
- Backend imports clean, pytest + vitest + tsc all green.
