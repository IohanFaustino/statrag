# Plan D — Productionize L3b (deepagents + synthesis skill) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Plan-C winner `synthesize_with_skill` (deepagents + `ow_skills/synthesis/SKILL.md`) into the live orchestrator-workers tutor stage as an opt-in "deep synthesis" path that renders as a normal `DeepTutorAnswer` at :5175.

**Architecture:** The deepagents agent does the hard cross-author synthesis and returns **free text**. A follow-on **nano "schema-fill" pass** (`_stream_structured`) maps that text into the streamable `DeepTutorAnswer` schema — preserving L3b's measured quality while keeping the existing renderer/SSE contract. The path is gated two ways that feed one `use_skill` flag: a **per-request** opt-in (`tutorWorkflow="orchestrator-deep"`, a selectable drafting-workflow at :5175) and an **ops** override (`TUTOR_OW_HARNESS=5`). Default behavior (`single`/`orchestrator`, level 0) is byte-for-byte unchanged; any L3b failure (deepagents missing, 429, empty, schema-fill fail) falls back to the L0 streaming synthesizer.

**Tech Stack:** Python 3.12 (FastAPI, openai, deepagents/langchain/langgraph, pydantic), React + Vite + TS (vitest), pytest. Backend :8766 + Vite :5175 via `./scripts/dev.sh`.

**Decisions locked at review (2026-06-04):** (1) nano schema-fill pass — not direct-JSON deepagents tool; (2) opt-in, L0 stays default; (3) harness level `TUTOR_OW_HARNESS=5` = "deepagents + skill", plus per-request `tutorWorkflow="orchestrator-deep"`.

**Spec:** `docs/superpowers/specs/2026-06-04-ow-harness-pland-design.md`
**Verdict it builds on:** `docs/superpowers/eval/2026-06-04-ow-deepagents-compare.md`

---

## File map

| File | Responsibility | Change |
|---|---|---|
| `src/services/chat/agents/ow_harness.py` | harness-level parse | bump max level 3→5; docstring |
| `src/services/chat/prompts/deep_tutor.py` | prompts | add `SCHEMA_FILL_PROMPT` |
| `src/services/chat/agents/orchestrator_workers.py` | OW stage | add `_schema_fill` helper; add `deep_synth` param; wire level-5/deep_synth → `synthesize_with_skill` → schema-fill → L0 fallback |
| `src/services/chat/agents/deep_tutor.py` | draft dispatch | allow `orchestrator-deep` workflow; pass `deep_synth` to OW |
| `src/services/chat/schemas/_core.py` | request schema | extend `tutorWorkflow` Literal with `"orchestrator-deep"` |
| `requirements.txt` | deps | add `deepagents` (import-guarded in code) |
| `web/src/data/tutorPipeline.ts` | modal card data | add deep-synth note to the drafting-workflow node |
| `web/src/components/PipelineDiagram.tsx` | modal card render + workflow selector | add `orchestrator-deep` option |
| `web/src/App.tsx` | UX state + progress | persist new workflow value; "~45 s" progress copy |
| `docs/services/chat-features/36-deep-tutor.md` | env table + mermaid | `TUTOR_OW_HARNESS=5` row; `orchestrator-deep` |
| `docs/services/chat-features/56-deep-synthesis-l3b.md` | per-feature doc | new |
| `docs/services/chat-features/55-ow-harness-ablation.md` | ablation doc | "shipped as opt-in L5" note |
| `docs/system/invariants.md`, `docs/system/changelog.md` | invariants + changelog | new invariant + entry |
| `src/services/chat/tests/test_ow_harness.py` | backend tests | level-5 parse + routing |
| `src/services/chat/tests/test_orchestrator_workers.py` | backend tests | schema-fill wiring + fallback (create if absent) |
| `web/src/components/PipelineDiagram.test.tsx` | web test | orchestrator-deep option renders |

**Branch:** create a fresh branch off `main` (already carries the merged planc stack): `git switch -c feat/ow-harness-pland main`.

---

### Task 1: Raise harness max level to 5

**Files:**
- Modify: `src/services/chat/agents/ow_harness.py:20` (and docstring lines 1-10)
- Test: `src/services/chat/tests/test_ow_harness.py`

- [ ] **Step 1: Write the failing test**

Add to `src/services/chat/tests/test_ow_harness.py`:

```python
def test_max_level_is_five(monkeypatch):
    monkeypatch.setenv("TUTOR_OW_HARNESS", "5")
    assert H.ow_harness_level() == 5
    monkeypatch.setenv("TUTOR_OW_HARNESS", "6")
    assert H.ow_harness_level() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py::test_max_level_is_five -v`
Expected: FAIL — at level 5 returns 0 (max still 3).

- [ ] **Step 3: Make minimal change**

In `src/services/chat/agents/ow_harness.py` change:

```python
_MAX_IMPLEMENTED_LEVEL = 5  # 0/1 (Plan A); 2/3 (Plan B); 5 = deepagents+skill (Plan D). 4 (subagents) rejected → falls through to L0.
```

Update the module docstring level list to add:
```
  4 = deepagents + subagents (rejected by Plan C; no branch → behaves as L0)
  5 = deepagents + synthesis SKILL.md  (Plan D — the shipped opt-in "deep synthesis")
```
and change the closing line to `Levels 0-5 implemented (Plan D).`

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -v`
Expected: PASS (incl. existing `test_max_level_is_three`, which asserts level 4 was clamped — update that test: at `"4"` it should now return `4`, at `"6"` return `0`).

Edit `test_max_level_is_three` accordingly:
```python
def test_levels_in_range_pass_clamp_above(monkeypatch):
    monkeypatch.setenv("TUTOR_OW_HARNESS", "5")
    assert H.ow_harness_level() == 5
    monkeypatch.setenv("TUTOR_OW_HARNESS", "9")
    assert H.ow_harness_level() == 0
```
(Rename the old `test_max_level_is_three` to this, or keep both with corrected expectations.)

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/ow_harness.py src/services/chat/tests/test_ow_harness.py
git commit -m "feat(pland): raise OW harness max level to 5 (deepagents+skill)"
```

---

### Task 2: Schema-fill prompt + helper

The schema-fill pass turns L3b free text into a streamed `DeepTutorAnswer`. It reuses `_stream_structured` (same schema, same SSE deltas) so the UI renders/streams unchanged.

**Files:**
- Modify: `src/services/chat/prompts/deep_tutor.py` (add `SCHEMA_FILL_PROMPT`)
- Modify: `src/services/chat/agents/orchestrator_workers.py` (add `_schema_fill`)
- Test: `src/services/chat/tests/test_orchestrator_workers.py` (create)

- [ ] **Step 1: Write the failing test**

Create `src/services/chat/tests/test_orchestrator_workers.py`:

```python
import asyncio
import src.services.chat.agents.orchestrator_workers as OW
from src.services.chat.schemas.output import DeepTutorAnswer


def test_schema_fill_calls_stream_structured_with_synthesis_text(monkeypatch):
    captured = {}

    async def fake_stream(messages, model, on_aspect_delta):
        captured["messages"] = messages
        captured["model"] = model
        return DeepTutorAnswer(tldr="t", definition="d", formal_statement="",
                               example_intuition="", applications="",
                               further_reading=""), {"definition": "d"}

    monkeypatch.setattr(OW, "_stream_structured", fake_stream)
    deep, aspects = asyncio.run(
        OW._schema_fill("What is variance?", "SYNTH TEXT", "nano", None)
    )
    assert deep is not None and deep.tldr == "t"
    # the synthesis text and question are handed to the fill model
    blob = "".join(m["content"] for m in captured["messages"])
    assert "SYNTH TEXT" in blob and "What is variance?" in blob
    assert captured["model"] == "nano"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_orchestrator_workers.py::test_schema_fill_calls_stream_structured_with_synthesis_text -v`
Expected: FAIL — `_schema_fill` does not exist.

- [ ] **Step 3: Add the prompt**

In `src/services/chat/prompts/deep_tutor.py` add:

```python
SCHEMA_FILL_PROMPT = (
    "You are a formatter. You are given a finished, correct tutor synthesis written "
    "as free prose, plus the original question. Re-express that synthesis into the "
    "DeepTutorAnswer schema fields WITHOUT adding, removing, or changing any claim, "
    "citation, author attribution, or formula. Preserve every author comparison and "
    "every [n] citation marker exactly as written. Distribute the existing content "
    "across the fields (tldr, definition, formal_statement, example_intuition, "
    "applications, further_reading); leave a field empty only if the synthesis has "
    "nothing for it. Keep all LaTeX math verbatim. Do NOT invent further_reading."
)
```

- [ ] **Step 4: Add the helper**

In `src/services/chat/agents/orchestrator_workers.py`, import the prompt (extend the existing `from src.services.chat.prompts.deep_tutor import (...)` block to include `SCHEMA_FILL_PROMPT`) and add:

```python
async def _schema_fill(
    query: str, synthesis_text: str, fill_model: str, on_aspect_delta
) -> tuple[DeepTutorAnswer | None, dict[str, str]]:
    """Map an L3b free-text synthesis into a streamed DeepTutorAnswer via one
    structured nano call. Streams the same _raw deltas the UI already renders."""
    user = (
        f"<question>\n{query}\n</question>\n\n"
        f"<synthesis>\n{synthesis_text}\n</synthesis>\n\n"
        f"Re-express the synthesis into the DeepTutorAnswer schema now."
    )
    messages = [
        {"role": "system", "content": SCHEMA_FILL_PROMPT},
        {"role": "user", "content": user},
    ]
    return await _stream_structured(messages, fill_model, on_aspect_delta)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_orchestrator_workers.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/prompts/deep_tutor.py src/services/chat/agents/orchestrator_workers.py src/services/chat/tests/test_orchestrator_workers.py
git commit -m "feat(pland): nano schema-fill pass (free text -> DeepTutorAnswer)"
```

---

### Task 3: Wire level-5 / deep_synth into the OW stage

`run_orchestrator_workers` gains a `deep_synth: bool` param. After workers produce briefs, if `deep_synth or ow_harness_level() == 5`, run `synthesize_with_skill` then `_schema_fill`; on empty/exception fall back to the existing L0 synthesizer.

**Files:**
- Modify: `src/services/chat/agents/orchestrator_workers.py` (signature + branch, near lines 124-188)
- Test: `src/services/chat/tests/test_orchestrator_workers.py`

- [ ] **Step 1: Write the failing tests**

Append to `src/services/chat/tests/test_orchestrator_workers.py`:

```python
from src.services.chat.schemas import Source
from src.services.chat.schemas.output import AuthorBrief, SynthesisPlan, WorkerTask


def _two_author_inputs():
    sources = [
        Source(rank=1, book="b1", chapter="1", section="s", excerpt="x",
               authors_short="Casella"),
        Source(rank=2, book="b2", chapter="1", section="s", excerpt="y",
               authors_short="Wasserman"),
    ]
    plan = SynthesisPlan(thesis="th", tasks=[
        WorkerTask(focus="Casella", source_ranks=[1]),
        WorkerTask(focus="Wasserman", source_ranks=[2]),
    ])
    return sources, plan


def test_deep_synth_routes_to_skill_then_schema_fill(monkeypatch):
    sources, plan = _two_author_inputs()

    async def fake_worker(query, thesis, author, srcs, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} sum",
                           key_points=[f"{author} kp"], source_ranks=[srcs[0].rank])
    monkeypatch.setattr(OW, "run_author_worker", fake_worker)

    calls = {}

    async def fake_skill(query, srcs, briefs):
        calls["skill"] = True
        return "DEEPAGENTS SYNTH", 10, 20
    import src.services.chat.agents.ow_deepagents as OWD
    monkeypatch.setattr(OWD, "synthesize_with_skill", fake_skill)

    async def fake_fill(query, text, model, cb):
        calls["fill_text"] = text
        return DeepTutorAnswer(tldr="ok", definition=text, formal_statement="",
                               example_intuition="", applications="",
                               further_reading=""), {}
    monkeypatch.setattr(OW, "_schema_fill", fake_fill)

    deep, _ = asyncio.run(OW.run_orchestrator_workers(
        "q", sources, plan, deep_synth=True))
    assert calls.get("skill") and calls["fill_text"] == "DEEPAGENTS SYNTH"
    assert deep.tldr == "ok"


def test_deep_synth_falls_back_to_L0_on_skill_failure(monkeypatch):
    sources, plan = _two_author_inputs()

    async def fake_worker(query, thesis, author, srcs, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} sum",
                           key_points=[f"{author} kp"], source_ranks=[srcs[0].rank])
    monkeypatch.setattr(OW, "run_author_worker", fake_worker)

    async def boom(query, srcs, briefs):
        raise RuntimeError("pip install deepagents")
    import src.services.chat.agents.ow_deepagents as OWD
    monkeypatch.setattr(OWD, "synthesize_with_skill", boom)

    seen = {}

    async def fake_stream(messages, model, cb):
        seen["L0"] = True
        return DeepTutorAnswer(tldr="L0", definition="d", formal_statement="",
                               example_intuition="", applications="",
                               further_reading=""), {}
    monkeypatch.setattr(OW, "_stream_structured", fake_stream)

    deep, _ = asyncio.run(OW.run_orchestrator_workers(
        "q", sources, plan, deep_synth=True))
    assert seen.get("L0") and deep.tldr == "L0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_orchestrator_workers.py -k deep_synth -v`
Expected: FAIL — `run_orchestrator_workers` has no `deep_synth` kwarg.

- [ ] **Step 3: Implement**

In `src/services/chat/agents/orchestrator_workers.py`, add `deep_synth: bool = False` to the `run_orchestrator_workers` keyword-only params (next to `on_briefs=None`). Then replace the existing `level == 3` block (lines ~178-188) with:

```python
    level = ow_harness_level()
    if level == 3:
        try:
            from src.services.chat.agents.ow_deepagents import synthesize_with_deepagents
            text = await synthesize_with_deepagents(query, sources, briefs)
            if text.strip():
                return _wrap_text_answer(text), {}
            logger.info("ow level-3 deepagents returned empty; falling back to L0 synth")
        except Exception:  # noqa: BLE001
            logger.exception("ow level-3 deepagents failed; falling back to L0 synthesizer")

    # L5 / per-request deep synthesis: deepagents + synthesis SKILL, then a nano
    # schema-fill pass renders it as a streamed DeepTutorAnswer. Any failure
    # (deepagents missing, empty, schema-fill None) falls through to L0 below.
    if deep_synth or level == 5:
        try:
            from src.services.chat.agents import ow_deepagents
            text, _it, _ot = await ow_deepagents.synthesize_with_skill(query, sources, briefs)
            if text.strip():
                fill_model = synth_model or settings.openai_model_nano
                if fill_model.startswith("deepseek"):
                    fill_model = settings.openai_model_nano
                deep_a, aspects_a = await _schema_fill(query, text, fill_model, on_aspect_delta)
                if deep_a is not None:
                    return deep_a, aspects_a
                logger.info("ow L5 schema-fill returned None; falling back to L0 synth")
            else:
                logger.info("ow L5 deepagents+skill returned empty; falling back to L0 synth")
        except Exception:  # noqa: BLE001
            logger.exception("ow L5 deepagents+skill failed; falling back to L0 synthesizer")
```

Note: reference `ow_deepagents.synthesize_with_skill` via the module (not a direct import binding) so the test's `monkeypatch.setattr(OWD, "synthesize_with_skill", ...)` is seen.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_orchestrator_workers.py -v`
Expected: PASS (both deep_synth tests + Task 2 test).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/orchestrator_workers.py src/services/chat/tests/test_orchestrator_workers.py
git commit -m "feat(pland): wire L5/deep_synth -> synthesize_with_skill -> schema-fill (L0 fallback)"
```

---

### Task 4: Extend request schema with `orchestrator-deep`

**Files:**
- Modify: `src/services/chat/schemas/_core.py:142`
- Test: `src/services/chat/tests/test_orchestrator_workers.py` (schema accept test) — or the existing schema test module if one exists; co-locate here for simplicity.

- [ ] **Step 1: Write the failing test**

Append to `src/services/chat/tests/test_orchestrator_workers.py`:

```python
def test_request_accepts_orchestrator_deep_workflow():
    from src.services.chat.schemas._core import ChatRequest
    req = ChatRequest(messages=[{"role": "user", "content": "hi"}],
                      tutorWorkflow="orchestrator-deep")
    assert req.tutorWorkflow == "orchestrator-deep"
```

(If `ChatRequest` requires other mandatory fields, fill the minimal valid set — check the class top in `_core.py` and adjust.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_orchestrator_workers.py::test_request_accepts_orchestrator_deep_workflow -v`
Expected: FAIL — pydantic rejects the literal.

- [ ] **Step 3: Implement**

In `src/services/chat/schemas/_core.py` change line 142:

```python
    tutorWorkflow: Literal["single", "orchestrator", "orchestrator-deep", "organize"] | None = None
```

Extend the comment above it:
```python
    # ``"orchestrator-deep"`` = orchestrator workers + the deepagents+SKILL deep
    #   synthesizer (Plan D, opt-in, ~45 s blocking; falls back to L0 on failure).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_orchestrator_workers.py::test_request_accepts_orchestrator_deep_workflow -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/schemas/_core.py src/services/chat/tests/test_orchestrator_workers.py
git commit -m "feat(pland): add orchestrator-deep to tutorWorkflow request enum"
```

---

### Task 5: Dispatch `orchestrator-deep` in deep_tutor

`_resolve_workflow` must accept `orchestrator-deep`; `_draft_coro` must route it to `run_orchestrator_workers(..., deep_synth=True)`.

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py:912-918` (`_resolve_workflow`) and `:2519-2537` (`_draft_coro`)
- Test: `src/services/chat/tests/test_orchestrator_workers.py` (resolve test)

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_resolve_workflow_passes_orchestrator_deep():
    from types import SimpleNamespace
    import src.services.chat.agents.deep_tutor as DT
    assert DT._resolve_workflow(SimpleNamespace(tutorWorkflow="orchestrator-deep")) == "orchestrator-deep"
    assert DT._resolve_workflow(SimpleNamespace(tutorWorkflow="single")) == "single"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_orchestrator_workers.py::test_resolve_workflow_passes_orchestrator_deep -v`
Expected: FAIL — `_resolve_workflow` collapses unknown to `"single"`, returns `"single"`.

- [ ] **Step 3: Implement `_resolve_workflow`**

In `src/services/chat/agents/deep_tutor.py`:

```python
def _resolve_workflow(req) -> str:
    """``"single"``, ``"orchestrator"``, ``"orchestrator-deep"``, or
    ``"organize"`` — request field over env default."""
    val = str(getattr(req, "tutorWorkflow", None) or _WORKFLOW_DEFAULT).lower()
    if val in ("orchestrator", "orchestrator-deep", "organize"):
        return val
    return "single"
```

- [ ] **Step 4: Implement `_draft_coro` routing**

Change the orchestrator branch (line ~2525) to handle both:

```python
        if workflow in ("orchestrator", "orchestrator-deep"):
            from src.services.chat.agents.orchestrator_workers import (
                run_orchestrator_workers,
            )
            deep_o, aspects_o = await run_orchestrator_workers(
                query, sources, plan,
                orchestrator_model=_WORKER_MODEL, worker_model=_WORKER_MODEL,
                synth_model=m_draft,
                figures=approved_figures, on_aspect_delta=_emit_aspect_delta,
                deep_synth=(workflow == "orchestrator-deep"),
            )
            if deep_o is not None:
                return deep_o, aspects_o
            logger.info("orchestrator returned no result; falling back to single draft")
```

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_orchestrator_workers.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_orchestrator_workers.py
git commit -m "feat(pland): route orchestrator-deep workflow to deep_synth OW path"
```

---

### Task 6: Add `deepagents` dependency (import-guarded)

Default paths never import deepagents; the L3/L5 branches lazy-import it and raise a clear error if missing (already covered by `test_deepagents_import_error_is_clear`). Adding it to requirements makes the opt-in path actually run in prod/dev.

**Files:**
- Modify: `requirements.txt`
- Test: `src/services/chat/tests/test_ow_harness.py` (existing import-guard test must still pass)

- [ ] **Step 1: Confirm the import-guard test exists and passes today**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py::test_deepagents_import_error_is_clear -v`
Expected: PASS.

- [ ] **Step 2: Add the dependency**

Append to `requirements.txt` (group with the other LLM libs; pin to the version proven in Plan C — check the installed version with `.venv/bin/pip show deepagents` and pin that):

```
deepagents
```

- [ ] **Step 3: Install + verify import works**

Run:
```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c "import deepagents; from deepagents import create_deep_agent; print('ok')"
```
Expected: `ok`.

- [ ] **Step 4: Verify default paths + suite unaffected**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: full chat suite green.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "build(pland): add deepagents dependency for opt-in deep synthesis"
```

---

### Task 7: Frontend — selectable `orchestrator-deep` workflow

The drafting-workflow selector lives in the modal pipeline node (`PipelineDiagram.tsx`, the "set" badge at line ~396). Add a fourth option so a user can opt in at :5175. `App.tsx` persists the value (it already stores `tutorWorkflow` as a free string, so no type change is needed there beyond default handling).

**Files:**
- Modify: `web/src/components/PipelineDiagram.tsx` (workflow options near line 385-410)
- Modify: `web/src/data/tutorPipeline.ts:104-105` (node desc)
- Test: `web/src/components/PipelineDiagram.test.tsx`

- [ ] **Step 1: Write the failing test**

In `web/src/components/PipelineDiagram.test.tsx` add (mirror an existing render test's props; set `tutorWorkflow="orchestrator-deep"`):

```tsx
  it("renders the deep-synthesis workflow option/label", () => {
    render(
      <PipelineDiagram
        /* ...same required props as the sibling tests... */
        tutorWorkflow="orchestrator-deep"
        onChange={() => {}}
      />,
    );
    expect(screen.getByText(/deep synthesis/i)).toBeInTheDocument();
  });
```

(Copy the exact prop set from the nearest existing `it(...)` block in this file so required props match.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/components/PipelineDiagram.test.tsx -t "deep-synthesis"`
Expected: FAIL — no "deep synthesis" label.

- [ ] **Step 3: Implement the option**

In `web/src/components/PipelineDiagram.tsx`, find the drafting-workflow selector options array (the values feeding the `set` control near line 396-405). Add:

```tsx
  { value: "orchestrator-deep", label: "Deep synthesis (slower ~45s)" },
```
after the existing `orchestrator` option. Ensure the active-label rendering maps `orchestrator-deep` → its label.

In `web/src/data/tutorPipeline.ts` extend the drafting-workflow node `desc` (line ~105) to mention:
```
… or deep synthesis (orchestrator workers + a deepagents agent that reads the synthesis SKILL and integrates the briefs; ~45 s, opt-in).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/components/PipelineDiagram.test.tsx`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/PipelineDiagram.tsx web/src/data/tutorPipeline.ts web/src/components/PipelineDiagram.test.tsx
git commit -m "feat(pland): selectable orchestrator-deep workflow in pipeline modal"
```

---

### Task 8: Latency UX — progress copy for the long synth

The deep path blocks ~30-57 s before the schema-fill stream starts. Show a clear progress state so it does not look hung. `App.tsx` already exposes `streamingPhase`; surface a deep-synth label while a request with `tutorWorkflow==="orchestrator-deep"` is in flight before first token.

**Files:**
- Modify: `web/src/App.tsx` (progress copy where `streamingPhase` is rendered)
- Test: `web/src/components/PipelineDiagram.test.tsx` or a small App-level test if one exists; otherwise verify visually in Task 10.

- [ ] **Step 1: Locate the streaming-phase indicator**

Run: `cd web && grep -rn "streamingPhase\|Synthesizing\|Drafting" src/`
Identify the component that renders the pre-token phase label (e.g. a status line / typing indicator).

- [ ] **Step 2: Add the deep-synth copy**

Where the phase label is derived, when the active request workflow is `orchestrator-deep` and no tokens have arrived yet, render:
```
Synthesizing across authors… (~45 s)
```
Keep it purely presentational (no new request field).

- [ ] **Step 3: Typecheck + build**

Run: `cd web && npx tsc --noEmit && npx vitest run`
Expected: no type errors; tests green.

- [ ] **Step 4: Commit**

```bash
git add web/src/App.tsx
git commit -m "feat(pland): ~45s progress copy for deep-synthesis path"
```

---

### Task 9: Docs + invariants + changelog (lockstep)

Per the CLAUDE.md "every pipeline stage spans synced artifacts" rule, the logic change is incomplete until docs/graphs/invariants reflect it.

**Files:**
- Modify: `docs/services/chat-features/36-deep-tutor.md` (env table + mermaid)
- Create: `docs/services/chat-features/56-deep-synthesis-l3b.md`
- Modify: `docs/services/chat-features/55-ow-harness-ablation.md`
- Modify: `docs/system/invariants.md`, `docs/system/changelog.md`
- Modify: CLAUDE.md (clear the Plan D pending row → mark shipped)

- [ ] **Step 1: Env table row** — in `docs/services/chat-features/36-deep-tutor.md`, update the `TUTOR_OW_HARNESS` row to add `5 = deepagents + synthesis SKILL (Plan D, shipped opt-in; needs deepagents installed; free text → nano schema-fill → DeepTutorAnswer; any failure → L0)`, and add to the `TUTOR_WORKFLOW`/`tutorWorkflow` row the `orchestrator-deep` value. Update the stage mermaid graph's synthesizer node note to mention the opt-in deep path.

- [ ] **Step 2: New per-feature doc** — create `docs/services/chat-features/56-deep-synthesis-l3b.md` covering: what it is (Plan C winner), the two triggers (`tutorWorkflow="orchestrator-deep"` per-request, `TUTOR_OW_HARNESS=5` ops), the free-text → schema-fill flow, latency (~45 s blocking) + L0 fallback, the Plan C numbers (quality 4.39 vs 3.96, fidelity 4.50 vs 3.39, ~$0.0046/answer), and a mermaid of: briefs → deepagents+SKILL → free text → nano schema-fill → DeepTutorAnswer (→ L0 on failure). Link the spec, plan, and verdict.

- [ ] **Step 3: Ablation doc** — in `docs/services/chat-features/55-ow-harness-ablation.md`, add a closing note: "L3b shipped as opt-in level 5 (Plan D) — see doc 56."

- [ ] **Step 4: Invariant** — add to `docs/system/invariants.md` a numbered invariant: "The deep-synthesis path (L5 / `orchestrator-deep`) must always fall back to the L0 streaming synthesizer on any failure (deepagents absent, empty output, schema-fill `None`); with the flag off, tutor output is byte-for-byte the level-0 behavior."

- [ ] **Step 5: Changelog** — add a dated entry to `docs/system/changelog.md` summarizing Plan D shipped (opt-in deep synthesis, schema-fill, deepagents dep).

- [ ] **Step 6: CLAUDE.md** — in the "⏳ Pending tasks" table, change the Plan D row status to ✅ shipped (or remove it) and drop the "Plan D context" / "Branch housekeeping" paragraphs that are now done.

- [ ] **Step 7: Commit**

```bash
git add docs/ CLAUDE.md
git commit -m "docs(pland): doc 56, env table, invariant, changelog; clear pending row"
```

---

### Task 10: Browser-verify on :5175 + full gate

**Files:** none (verification).

- [ ] **Step 1: Ensure system is up**

Run: `./scripts/dev.sh` (background) and confirm `curl -s localhost:5175/api/health` → `{"status":"ok"}`.

- [ ] **Step 2: Full backend + web gate**

Run:
```bash
.venv/bin/python -m pytest src/services/chat/tests/ -q
.venv/bin/ruff check src/services/chat/
.venv/bin/mypy src/services/chat/agents/orchestrator_workers.py src/services/chat/agents/ow_harness.py
cd web && npx tsc --noEmit && npx vitest run
```
Expected: all green.

- [ ] **Step 3: Browser-verify the opt-in path (uses claude-in-chrome on :5175)**

1. Open `http://localhost:5175`, tutor mode, a multi-author fan-out question (e.g. "Compare how different authors define and motivate the bias–variance tradeoff").
2. Open the pipeline (i) modal, set drafting workflow → **Deep synthesis (slower ~45s)**.
3. Send. Confirm: the "Synthesizing across authors… (~45 s)" progress shows; then a fully-populated `DeepTutorAnswer` renders (tldr, definition, formal_statement, example_intuition, applications, further_reading), with citations `[n]` and LaTeX math intact.
4. Confirm the modal card visually matches `docs/common ground/Elements/index.html` (Chat & deep-tutor page) for the drafting-workflow node.

- [ ] **Step 4: Browser-verify default is unchanged**

Switch workflow back to **Single**, ask the same question, confirm normal streaming + a normal `DeepTutorAnswer`. (Acceptance #2: flag off → current behavior.)

- [ ] **Step 5: Verify ops trigger + fallback (optional, terminal)**

With `TUTOR_OW_HARNESS=5` set and deepagents installed, an `orchestrator` request uses the skill synth. Temporarily uninstall deepagents (or simulate `synthesize_with_skill` raising) and confirm the answer still returns via L0 (no user-visible error).

- [ ] **Step 6: Finish the branch**

Use `superpowers:finishing-a-development-branch` to choose merge/PR. Acceptance criteria recap to confirm before finishing:
1. Flag on → fully-populated `DeepTutorAnswer` from L3b at :5175. ✅
2. Flag off → byte-for-byte current behavior; any L3b failure → L0. ✅
3. Full suite + web tests green; deepagents import-guarded. ✅
4. Latency UX shows progress, not hung. ✅

---

## Self-review notes

- **Spec coverage:** hurdle 1 → Tasks 2-3 (schema-fill); hurdle 2 → Tasks 7-8 (opt-in + progress, L0 default); hurdle 3 → Tasks 1,3-6 (level 5 + deps + lockstep). Acceptance 1-4 → Task 10. Out-of-scope (L4, model sweep, making default) honored.
- **Type/name consistency:** `_schema_fill(query, synthesis_text, fill_model, on_aspect_delta)` defined Task 2, called Task 3; `deep_synth` kwarg defined Task 3, passed Task 5; `synthesize_with_skill` returns `(text, in_tok, out_tok)` per existing `ow_deepagents.py` — Task 3 unpacks 3-tuple. `tutorWorkflow="orchestrator-deep"` literal added Task 4, resolved Task 5, selectable Task 7.
- **Fallback chain:** L5 empty/exception/schema-fill-None all reach the existing L0 `_stream_structured` synthesizer below the branch — verified by the structure of Task 3's replacement (the branch `return`s only on success).
