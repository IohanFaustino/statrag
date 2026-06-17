# Tutor Finalize+Verify Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. **Dispatch isolation (CLAUDE.md rule 0): implementers run in a dedicated git worktree, never the live checkout; implementers run ZERO git.** Implementers are Ollama-cloud agents via OpenCode.

**Goal:** Stop `nano` from mounting the user-facing tutor answer — add a silent cheap draft → strong **finalizer** that streams a complete (every sub-question), correctly-structured (one box per definition) answer, plus fix the box-overflow CSS and the KPSS/ADF image-retrieval bug at their true layers.

**Architecture:** New `_stream_finalize` stage in `deep_tutor.py` between the draft (`:2971`) and seam-guard (`:2986`). The `nano` draft runs **silent** (`on_aspect_delta=None`); the finalizer reuses `_stream_structured` with a new system prompt + the draft injected into the user message, and streams via `_emit_aspect_delta`. Pure-code guards drop broken figure refs and log uncovered facets. CSS + image bugs fixed at render/retrieval layers.

**Tech Stack:** Python 3.12 (FastAPI, pydantic, openai async, asyncio), pytest; React/TS + KaTeX + vitest; env-flag wiring (`TUTOR_FINALIZE`, `TUTOR_FINALIZE_MODEL`, `stageModels["finalize"]`).

**Reference:** spec `docs/superpowers/specs/2026-06-17-tutor-finalize-stage-design.md`. Existing patterns to mirror: `_stream_draft` (`:1947`), `_stream_structured` (`:1995`), `_seam_guard` (`:1920`), `_resolve_stage_model` (`:975`), `_build_user_message` (used at `:1972`).

---

## Task 1: Finalizer prompt + user-message builder

**Files:**
- Modify: `src/services/chat/prompts/deep_tutor.py` (add `DEEP_TUTOR_FINALIZE_INSTRUCTIONS`)
- Modify: `src/services/chat/agents/deep_tutor.py` (add `_build_finalize_message`)
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write the failing test** — `_build_finalize_message` embeds the draft, every facet, and a one-box-per-definition instruction.

```python
def test_build_finalize_message_includes_draft_and_facets():
    from src.services.chat.agents.deep_tutor import _build_finalize_message
    draft_aspects = {"definition": "Stationarity means ... [1]", "tldr": "x"}
    facets = ["strict stationarity", "weak stationarity", "unit root"]
    msg = _build_finalize_message(
        "What is stationarity, its versions, and a unit root?",
        draft_aspects, sources=[], facets=facets, figures=[],
    )
    # every facet the answer must cover is named
    for f in facets:
        assert f in msg
    # the draft material is carried in
    assert "Stationarity means" in msg
    # the structural contract is stated
    assert "one" in msg.lower() and "definition" in msg.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_build_finalize_message_includes_draft_and_facets -v`
Expected: FAIL — `_build_finalize_message` not defined.

- [ ] **Step 3: Add the prompt constant** in `src/services/chat/prompts/deep_tutor.py` (after `DEEP_TUTOR_INSTRUCTIONS`):

```python
DEEP_TUTOR_FINALIZE_INSTRUCTIONS = """You are the FINALIZER for a textbook tutor answer.
You receive a rough draft plus the sources, the facets (sub-questions) the answer
MUST cover, and approved figures. Produce the final answer as a DeepTutorAnswer.

Hard rules:
- COVER EVERY FACET. If the draft skipped a sub-question, answer it. Weave all
  sub-questions into ONE continuous narrative arc (no disconnected sections).
- ONE formal statement PER definition. Put each distinct definition/theorem in
  its OWN formal_statements[] entry (kind/label/statement/cite) — never cram two
  definitions into one block. Quote formal statements verbatim from the sources.
- Every bare formula carries explanation: no orphan `\\rho = 1` without saying
  what it means in the surrounding prose.
- Math delimiters well-formed: inline `$...$`, display `$$...$$` on its own line.
- Keep the draft's [N] citations and figure [Fn] markers; do not invent sources.
- Preserve any <recovered_equations> / <formal_definitions> verbatim blocks.
"""
```

- [ ] **Step 4: Add `_build_finalize_message`** in `deep_tutor.py` (near `_build_user_message`). It reuses `_build_user_message` for the source/figure context and prepends the draft + facet checklist:

```python
def _build_finalize_message(query, draft_aspects, sources, facets, figures=None):
    base = _build_user_message(query, sources, figures=figures or [], plan=None)
    draft_md = assemble_markdown(draft_aspects)
    facet_list = "\n".join(f"- {f}" for f in (facets or []))
    return (
        f"<facets_to_cover>\n{facet_list}\n</facets_to_cover>\n\n"
        f"<draft>\n{draft_md}\n</draft>\n\n"
        f"Rewrite the draft into the final answer, covering every facet above and "
        f"using one formal_statements[] entry per definition.\n\n{base}"
    )
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_build_finalize_message_includes_draft_and_facets -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/prompts/deep_tutor.py src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "feat(tutor): finalizer prompt + finalize message builder"
```

---

## Task 2: `_stream_finalize` + orchestration wiring (silent draft → finalizer streams)

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py` (add `_stream_finalize`; wire env + call site `:2949-2987`)
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write the failing test** — when `TUTOR_FINALIZE=1`, the finalizer model is used to produce the streamed answer; when off, draft streams as today.

```python
@pytest.mark.asyncio
async def test_finalize_stage_runs_when_enabled(monkeypatch):
    import src.services.chat.agents.deep_tutor as dt
    monkeypatch.setenv("TUTOR_FINALIZE", "1")
    calls = []
    async def fake_stream_structured(messages, model, on_aspect_delta=None):
        calls.append(model)
        if on_aspect_delta:
            on_aspect_delta("_raw", "final text")
        return dt.DeepTutorAnswer(tldr="t", definition="d", formal_statement="",
                                  example_intuition="e", applications="a",
                                  further_reading="f", citations=[]), \
               {k: "x" for k in dt.ASPECT_HEADINGS}
    monkeypatch.setattr(dt, "_stream_structured", fake_stream_structured)
    deep, aspects = await dt._stream_finalize(
        "q", {"definition": "draft"}, sources=[], facets=["a"],
        figures=[], on_aspect_delta=lambda *a: None, model="deepseek-v4-pro",
    )
    assert "deepseek-v4-pro" in calls
    assert deep is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_finalize_stage_runs_when_enabled -v`
Expected: FAIL — `_stream_finalize` not defined.

- [ ] **Step 3: Add `_stream_finalize`** (mirrors `_stream_draft` `:1947`, but builds the finalize message + uses `DEEP_TUTOR_FINALIZE_INSTRUCTIONS`):

```python
async def _stream_finalize(query, draft_aspects, sources, facets, figures,
                           on_aspect_delta, model):
    from src.services.chat.prompts.deep_tutor import DEEP_TUTOR_FINALIZE_INSTRUCTIONS  # noqa: PLC0415
    from src.services.chat.llm.router import is_structured_output_capable  # noqa: PLC0415
    user = _build_finalize_message(query, draft_aspects, sources, facets, figures)
    messages = [
        {"role": "system", "content": _maybe_append_groq_addendum(DEEP_TUTOR_FINALIZE_INSTRUCTIONS, model)},
        {"role": "user", "content": user},
    ]
    if not is_structured_output_capable(model):
        return await _stream_draft_via_router(model, messages,
                                              {k: "" for k in ASPECT_HEADINGS}, on_aspect_delta)
    return await _stream_structured(messages, model, on_aspect_delta)
```

- [ ] **Step 4: Add env flag + model resolver** near the other `TUTOR_*` flags / `m_draft`:

```python
FINALIZE_ON = os.environ.get("TUTOR_FINALIZE", "1") not in ("0", "false", "")
```
And where `m_draft` is resolved (near `:2724`), add:
```python
m_finalize = _resolve_stage_model("finalize", os.environ.get("TUTOR_FINALIZE_MODEL", "") or settings.deepseek_model, sm)
```

- [ ] **Step 5: Rewire the draft/stream block** (`:2955-2987`). Run the draft **silent** when finalize is on, then stream the finalizer:

```python
    _finalize = FINALIZE_ON and not (sm or {}).get("finalize") == "off"
    async def _draft_coro():
        return await _stream_draft(
            query, sources, figures=approved_figures,
            on_aspect_delta=(None if _finalize else _emit_aspect_delta),
            model=m_draft, plan=plan, recovered_block=recovered_block,
        )
    draft_task = asyncio.create_task(_draft_coro())
    while not draft_task.done() or not sse_queue.empty():
        try:
            ev = await asyncio.wait_for(sse_queue.get(), timeout=0.1)
            yield ev
        except asyncio.TimeoutError:
            continue
    deep, aspects = await draft_task
    timings["draft_ms"] = int((time.monotonic() - t_draft) * 1000)

    if _finalize:
        async def _finalize_coro():
            return await _stream_finalize(query, aspects, sources, facets,
                                          approved_figures, _emit_aspect_delta, m_finalize)
        fin_task = asyncio.create_task(_finalize_coro())
        while not fin_task.done() or not sse_queue.empty():
            try:
                ev = await asyncio.wait_for(sse_queue.get(), timeout=0.1)
                yield ev
            except asyncio.TimeoutError:
                continue
        deep, aspects = await fin_task
        timings["finalize_ms"] = int((time.monotonic() - t_draft) * 1000) - timings["draft_ms"]
```

- [ ] **Step 6: Run the new test + full suite**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -q | tail -3`
Expected: PASS, count ≥ prior baseline.

- [ ] **Step 7: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "feat(tutor): silent draft -> streaming finalizer stage (TUTOR_FINALIZE)"
```

---

## Task 3: Pure-code verify guards (drop broken figures, log missing facets)

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py` (add `_verify_finalized`, call before `_convert_to_tutor_answer` `:3041`)
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_verify_drops_broken_figure_refs_and_reports_missing_facets():
    from src.services.chat.agents.deep_tutor import _verify_finalized
    aspects = {"definition": "See [F1] and [F2].", "applications": "Use it."}
    # F1 url empty -> broken; F2 ok
    figures = [type("F", (), {"url": ""})(), type("F", (), {"url": "http://x/y.png"})()]
    cleaned, missing = _verify_finalized(aspects, figures, facets=["unit root", "weak stationarity"])
    assert "[F1]" not in cleaned["definition"]      # broken ref stripped
    assert "[F2]" in cleaned["definition"]           # valid ref kept
    assert "unit root" in missing and "weak stationarity" in missing  # neither facet keyword present
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_verify_drops_broken_figure_refs_and_reports_missing_facets -v`
Expected: FAIL — `_verify_finalized` not defined.

- [ ] **Step 3: Implement `_verify_finalized`** (pure code, no model):

```python
def _verify_finalized(aspects, figures, facets):
    # figure index (1-based) -> ok if url is truthy
    ok = {i + 1 for i, f in enumerate(figures or []) if (getattr(f, "url", "") or "").strip()}
    cleaned = {}
    for k, v in aspects.items():
        def _strip(m):
            return m.group(0) if int(m.group(1)) in ok else ""
        v = re.sub(r"(?<!\w)\[F(\d+)\]", _strip, v or "")
        cleaned[k] = re.sub(r"  +", " ", v)
    blob = " ".join(cleaned.values()).lower()
    missing = [f for f in (facets or []) if f.lower() not in blob]
    if missing:
        logger.info("finalize verify: %d facet(s) not surfaced: %s", len(missing), "; ".join(missing))
    return cleaned, missing
```

- [ ] **Step 4: Wire it** just before `_convert_to_tutor_answer` (`:3041`), only when finalize ran:

```python
    if _finalize:
        aspects, _missing_facets = _verify_finalized(aspects, approved_figures, facets)
        _mirror_aspects(deep, aspects)
```

- [ ] **Step 5: Run new test + full suite**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -q | tail -3`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "feat(tutor): pure-code verify guards (drop broken figures, log missing facets)"
```

---

## Task 4: Box-overflow CSS fix + live KaTeX diagnosis

**Files:**
- Modify: `web/src/styles/tutor.css:100` (`.tutor-view__quote`)
- (Conditional) Modify: `web/src/components/views/TutorView.tsx` (`normalizeMathDelimiters` / tokenizer) — only per diagnosis
- Test: `web/src/components/views/TutorView.*.test.tsx`

- [ ] **Step 1: CSS overlap fix (one line).** In `.tutor-view__quote` add:

```css
  overflow-x: auto;
  min-width: 0;
```

- [ ] **Step 2: Live KaTeX diagnosis (orchestrator + debug_Advisor).** This is diagnose-first — root cause unknown. On `:5175`, run the three failing queries; capture the exact raw text that mis-renders (DB row + DOM). Consult `debug_Advisor` to localize: model output vs `normalizeMathDelimiters` gap vs tokenizer (`renderInlineWithCites` `:603`) vs unbalanced-`$` disable path (`:616`). Produce a diagnosis with the offending input quoted.

- [ ] **Step 3: Fix per diagnosis + regression test.** Add a frontend test asserting the captured offending input now renders without raw LaTeX leak. (Code is filled in from the diagnosis — do not guess before Step 2.)

- [ ] **Step 4: Run frontend tests**

Run: `cd web && npx vitest run src/components/views/TutorView 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/styles/tutor.css web/src/components/views/TutorView.tsx web/src/components/views/TutorView.*.test.tsx
git commit -m "fix(tutor): inline math no longer overlaps formal-statement box; katex render fix"
```

---

## Task 5: KPSS/ADF image-retrieval bug — diagnose + fix

**Files:**
- Diagnose: `src/services/chat/retrievers/image_density.py` (`fetch_image_candidates`), `src/services/chat/agents/image_judge.py` (`resolve_image_for_vision`, `judge_image_candidates`), call sites `deep_tutor.py:2871-2885`
- Test: `src/services/chat/tests/` (regression that fails on current code)

- [ ] **Step 1: Reproduce (orchestrator).** Run *"What is the KPSS and ADF test of stationarity?"* on `:5175`; capture the exact error (SSE `error` event / backend traceback / broken image URL in `figures_full`).

- [ ] **Step 2: Localize (debug_Advisor).** Hand the repro to `debug_Advisor` to find the fault: exception in `fetch_image_candidates`, `resolve_image_for_vision` returning a bad ref, or a malformed image URL reaching the frontend. Output: root cause + the input that triggers it.

- [ ] **Step 3: Write a regression test that fails on current code** (shape depends on diagnosis — e.g. feed the triggering candidate to the failing function and assert it no longer throws / no longer yields a broken URL).

- [ ] **Step 4: Fix at source; re-run.**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q -k "image" | tail -3`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A src/services/chat
git commit -m "fix(tutor): KPSS/ADF image retrieval no longer errors"
```

---

## Task 6: Finalizer bake-off (decide the default model)

**Files:**
- Create: `src/services/chat/eval/finalize_bakeoff.py` (small manual runner; `ponytail:` one-off, delete-able)

- [ ] **Step 1: Confirm gemini-3-pro reachable.** `grep "gemini" src/services/chat/llm/router.py` (prefix-routes); make a one-shot structured call with `model="gemini-3-pro"`. If it errors, fall back to `gemini-2.5-pro` and note it.

- [ ] **Step 2: Run the three finalizers** (`deepseek-v4-pro`, `gpt-5.4-2026-03-05`, `gemini-3-pro`) on the two queries: *"What is stationarity? What are its versions? What is a unit root?"* and *"What is the KPSS and ADF test of stationarity?"* via `TUTOR_FINALIZE_MODEL`. Capture each final answer.

- [ ] **Step 3: Score (orchestrator inspects).** For each: (a) every sub-question answered? (b) LaTeX renders clean on `:5175`? (c) one box per definition? Pick the winner.

- [ ] **Step 4: Set default.** Set the chosen model as `TUTOR_FINALIZE_MODEL` default (Task 2 Step 4 default already `settings.deepseek_model`; change only if a different model wins). Record the verdict in the changelog (Task 7).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/eval/finalize_bakeoff.py src/services/chat/agents/deep_tutor.py
git commit -m "chore(tutor): finalizer bake-off + default model"
```

---

## Task 7: Lockstep — docs, modal, invariants, changelog, live verify

**Files:**
- Create: `docs/services/chat-features/58-tutor-finalize.md`
- Modify: `docs/services/chat-features/36-deep-tutor.md` (mermaid node + env table)
- Modify: `web/src/data/tutorPipeline.ts` + `web/src/components/PipelineDiagram.tsx` (+ `PipelineDiagram.test.tsx`)
- Modify: `docs/common ground/Elements/modes/tutor.html`
- Modify: `docs/system/invariants.md`, `docs/system/changelog.md`

- [ ] **Step 1: Add a "Finalize+verify" node** to the modal pipeline data (`tutorPipeline.ts`) between draft and seam-guard; update `PipelineDiagram.test.tsx` for the new node.
- [ ] **Step 2: Add the mermaid node** + `TUTOR_FINALIZE`/`TUTOR_FINALIZE_MODEL` env rows to `36-deep-tutor.md`; write `58-tutor-finalize.md` (stage purpose, contract, guards, model choice from Task 6).
- [ ] **Step 3: Mirror the stage** into HTML `tutor.html` and add invariant + changelog entries (incl. the bake-off verdict).
- [ ] **Step 4: Run all gates.**

```bash
.venv/bin/python -m pytest src/services/chat/tests/ -q | tail -3
cd web && npx vitest run 2>&1 | tail -5 && npx tsc --noEmit
```
Expected: all green, tsc clean.

- [ ] **Step 5: Live verify on `:5175`** (orchestrator, Law 1): run all three failing queries — every sub-question answered, one box per definition, KaTeX paints with no overlap/leak, images load. Confirm modal matches `tutor.html`.

- [ ] **Step 6: Commit**

```bash
git add -A docs web
git commit -m "docs(tutor): finalize stage lockstep (doc 58, modal node, mermaid, invariants, changelog)"
```

---

## Self-review notes

- **Spec coverage:** C1→Tasks 1-2; C2→Task 3; C3→Task 4; C4→Task 5; C5→Task 6; lockstep→Task 7. All five components covered.
- **Diagnose-first honesty:** Tasks 4 (KaTeX) and 5 (image) have unknown root cause — their fix steps are gated behind a `debug_Advisor` diagnosis with the offending input quoted; no fabricated fix code.
- **Naming consistency:** `_stream_finalize`, `_build_finalize_message`, `_verify_finalized`, `m_finalize`, `FINALIZE_ON`, `TUTOR_FINALIZE` / `TUTOR_FINALIZE_MODEL` / `stageModels["finalize"]` used consistently across tasks.
- **Baseline:** record the current `test_deep_tutor.py` pass count before Task 1 so "≥ baseline" is checkable.
