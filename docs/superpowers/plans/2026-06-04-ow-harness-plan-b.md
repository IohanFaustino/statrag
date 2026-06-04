# Orchestrator-Workers Harness Ablation — Plan B (L2/L3 + re-baseline A/B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-baseline the orchestrator-workers ablation on scoped sources + a content-bearing fidelity metric, then add a structured-handoff level (L2, no deepagents, production-wired) and a deepagents-synthesizer level (L3, eval experiment), and A/B all three to attribute any gain to *structure* (L2−L0) vs the *deepagents agent* (L3−L2).

**Architecture:** Brief-formatting + level dispatch live in `ow_harness.py`/`orchestrator_workers.py` gated by `TUTOR_OW_HARNESS` (L0 default + fallback). The deepagents synthesizer is an isolated experiment module (`ow_deepagents.py`, lazy import, not in prod deps). The eval drives L0/L2/L3 over scoped frozen sources with one nano judge. Model held constant at nano.

**Tech Stack:** Python 3.12, existing chat infra, `langchain_openai`, `deepagents` (manual install for L3 only), pytest.

**Spec:** `docs/superpowers/specs/2026-06-04-ow-harness-planb-design.md` (+ parent `2026-06-04-orchestrator-workers-harness-ablation-design.md`).

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/services/chat/agents/ow_harness.py` | `structured_briefs_block`, `content_bearing`, `_MAX_IMPLEMENTED_LEVEL=3` |
| `src/services/chat/agents/orchestrator_workers.py` | level-gated brief formatting (L2) + L3 deepagents dispatch + `_wrap_text_answer` |
| `src/services/chat/agents/ow_deepagents.py` | deepagents synthesizer experiment (lazy import) |
| `src/services/chat/eval/ow_harness_compare.py` | scoped BOOKS, content-bearing fidelity, L0/L2/L3 run loop |
| `src/services/chat/tests/test_ow_harness.py` | unit tests (pure helpers, level dispatch, fidelity filter) |
| docs 36/55 + changelog | env row, feature doc, changelog |

Verified facts: synth user message at `orchestrator_workers.py:175` uses `f"{_format_author_briefs(briefs)}\n\n"`. `AuthorBrief` = `{author,summary,key_points,source_ranks}`. `DeepTutorAnswer` required text fields: `tldr, definition, formal_statement, example_intuition, applications, further_reading` (empty strings allowed). `ow_harness_level()` reads `TUTOR_OW_HARNESS`. Book slugs `hansen, wooldridge, stock_watson, gujarati, baltagi, pesaran, islp, murphy` all exist.

---

## Task 1: Harness helpers — structured briefs + content-bearing filter + level cap

**Files:** Modify `src/services/chat/agents/ow_harness.py`; Test `src/services/chat/tests/test_ow_harness.py`

- [ ] **Step 1: Write the failing test (append)**

```python
import json as _json
from src.services.chat.schemas.output import AuthorBrief


def test_structured_briefs_block_is_json():
    briefs = [AuthorBrief(author="Hansen", summary="s1", key_points=["k1"], source_ranks=[1])]
    block = H.structured_briefs_block(briefs)
    assert "<author_briefs_json>" in block and "</author_briefs_json>" in block
    inner = block.split("<author_briefs_json>")[1].split("</author_briefs_json>")[0].strip()
    data = _json.loads(inner)
    assert data == [{"author": "Hansen", "summary": "s1", "key_points": ["k1"], "source_ranks": [1]}]


def test_content_bearing_filters_no_info():
    briefs = [
        AuthorBrief(author="A", summary="The source does not discuss this.", key_points=[]),
        AuthorBrief(author="B", summary="Real treatment.", key_points=["kp"]),
        AuthorBrief(author="C", summary="", key_points=[]),
    ]
    kept = H.content_bearing(briefs)
    assert [b.author for b in kept] == ["B"]


def test_max_level_is_three(monkeypatch):
    monkeypatch.setenv("TUTOR_OW_HARNESS", "3")
    assert H.ow_harness_level() == 3
    monkeypatch.setenv("TUTOR_OW_HARNESS", "4")
    assert H.ow_harness_level() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -k "structured or content_bearing or max_level" -v`
Expected: FAIL — helpers not defined / `_MAX_IMPLEMENTED_LEVEL` still 1-or-3-mismatch.

- [ ] **Step 3: Implement**

In `ow_harness.py`, set `_MAX_IMPLEMENTED_LEVEL = 3`. Add at the end:

```python
import json as _json


def structured_briefs_block(briefs) -> str:
    """Render briefs as a JSON block (the L2 structured handoff)."""
    data = [{"author": b.author, "summary": b.summary,
             "key_points": list(b.key_points), "source_ranks": list(b.source_ranks)}
            for b in briefs]
    return "<author_briefs_json>\n" + _json.dumps(data, ensure_ascii=False) + "\n</author_briefs_json>"


_NO_INFO_MARKERS = ("not discuss", "does not", "no mention", "not address",
                    "do not discuss", "doesn't", "no information")


def content_bearing(briefs) -> list:
    """Drop 'no-info' briefs (summary disclaims content or empty key_points)."""
    out = []
    for b in briefs:
        s = (b.summary or "").lower()
        if not b.key_points and not b.summary:
            continue
        if any(m in s for m in _NO_INFO_MARKERS) and len(b.key_points) == 0:
            continue
        out.append(b)
    return out
```

(Adjust the existing module docstring's "Plan A implements 0 and 1 only" line to "Levels 0-3 implemented (Plan B); level 4 reserved.")

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -v`
Expected: PASS. (The Plan-A `test_level_parse_default_and_clamp` asserted `TUTOR_OW_HARNESS=9 → 0`; still true. It also asserted `=2 → 2`; still true.)

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/ow_harness.py src/services/chat/tests/test_ow_harness.py
git commit -m "feat(ow-harness): structured-briefs block + content-bearing filter + level cap 3"
```

---

## Task 2: deepagents synthesizer experiment module

**Files:** Create `src/services/chat/agents/ow_deepagents.py`; Test `src/services/chat/tests/test_ow_harness.py`

> The exact deepagents file-preload API (StoreBackend / `create_file_data`) is validated live in Task 6. Unit tests here cover only the pure parts (markdown formatter + the lazy-import error). The implementer SHOULD consult the `deep-agents-memory` and `deep-agents-core` skills for the preload API; the code below is the documented baseline.

- [ ] **Step 1: Write the failing test (append)**

```python
def test_brief_md_formats():
    from src.services.chat.agents import ow_deepagents as DA
    from src.services.chat.schemas.output import AuthorBrief
    md = DA._brief_md(AuthorBrief(author="Hansen", summary="sum", key_points=["k1", "k2"]))
    assert "Hansen" in md and "sum" in md and "k1" in md and "k2" in md


def test_deepagents_import_error_is_clear(monkeypatch):
    import sys
    from src.services.chat.agents import ow_deepagents as DA
    # Simulate deepagents missing.
    monkeypatch.setitem(sys.modules, "deepagents", None)
    import asyncio
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="pip install deepagents"):
        asyncio.run(DA.synthesize_with_deepagents("q", [], []))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -k "brief_md or import_error" -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# src/services/chat/agents/ow_deepagents.py
"""Harness level 3: a deepagents synthesizer agent (eval experiment).

Our nano workers still produce AuthorBriefs; here each brief is preloaded as a file
into a deepagents agent's virtual filesystem, and the agent reads the brief files and
writes the synthesis. Returns free text (no DeepTutorAnswer schema — judged as text by
the eval). deepagents is NOT a prod dependency; install it manually to run level 3.

See `deep-agents-core` / `deep-agents-memory` skills for the backend/preload API.
"""
from __future__ import annotations

import asyncio
import logging
import re

from src.core.config import settings

logger = logging.getLogger(__name__)

_SYNTH_INSTRUCTIONS = (
    "You synthesize multiple authors' briefs into one tutor answer. The briefs are "
    "files under /briefs/. READ every /briefs/*.md file, then write a single coherent "
    "answer that integrates them into one throughline and COMPARES the authors "
    "explicitly (not a concatenation). Ground every claim in the briefs."
)


def _slug(author: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (author or "author").lower()).strip("-") or "author"


def _brief_md(b) -> str:
    kps = "\n".join(f"- {k}" for k in b.key_points)
    return f"# {b.author}\n\n{b.summary}\n\n{kps}\n"


async def synthesize_with_deepagents(query: str, sources, briefs) -> str:
    """Run the deepagents synthesizer over preloaded brief files. Returns the answer
    text. Raises RuntimeError if deepagents is not installed."""
    try:
        import deepagents  # noqa: F401
        from deepagents import create_deep_agent
        from deepagents.backends import StoreBackend
        from deepagents.backends.utils import create_file_data
        from langgraph.store.memory import InMemoryStore
    except (ImportError, TypeError) as e:  # None-in-sys.modules raises TypeError
        raise RuntimeError("pip install deepagents to run harness level 3") from e
    from langchain_openai import ChatOpenAI

    store = InMemoryStore()
    for b in briefs:
        store.put(namespace=("filesystem",),
                  key=f"/briefs/{_slug(b.author)}.md",
                  value=create_file_data(_brief_md(b)))

    model = ChatOpenAI(model=settings.openai_model_nano, temperature=0.0)
    agent = create_deep_agent(
        model=model, tools=[], system_prompt=_SYNTH_INSTRUCTIONS,
        backend=lambda rt: StoreBackend(rt), store=store)
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user",
                       "content": f"Question: {query}\nSynthesize the briefs now."}]},
        {"configurable": {"thread_id": "ow-l3"}})
    msgs = result.get("messages", []) if isinstance(result, dict) else []
    return (msgs[-1].content if msgs else "") or ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -k "brief_md or import_error" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/ow_deepagents.py src/services/chat/tests/test_ow_harness.py
git commit -m "feat(ow-harness): deepagents synthesizer experiment module (lazy import)"
```

---

## Task 3: Wire L2 structured + L3 dispatch into the workflow

**Files:** Modify `src/services/chat/agents/orchestrator_workers.py`; Test `src/services/chat/tests/test_ow_harness.py`

- [ ] **Step 1: Write the failing test (append)**

```python
def test_level2_uses_structured_block(monkeypatch):
    from src.services.chat.agents import orchestrator_workers as OW
    from src.services.chat.schemas.output import AuthorBrief, DeepTutorAnswer
    monkeypatch.setenv("TUTOR_OW_HARNESS", "2")
    srcs = [_src(1, "Hansen"), _src(2, "Wooldridge")]
    captured = {}

    async def fake_worker(query, thesis, author, s, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} sum", key_points=["kp"], source_ranks=[s[0].rank])

    async def fake_stream(messages, *a, **k):
        captured["user"] = messages[1]["content"]
        return DeepTutorAnswer(tldr="", definition="d", formal_statement="",
                               example_intuition="", applications="", further_reading=""), {}

    with patch.object(OW, "run_author_worker", side_effect=fake_worker), \
         patch.object(OW, "_stream_structured", side_effect=fake_stream):
        asyncio.run(OW.run_orchestrator_workers("q", srcs, None))
    assert "<author_briefs_json>" in captured["user"]


def test_level3_routes_to_deepagents(monkeypatch):
    from src.services.chat.agents import orchestrator_workers as OW
    from src.services.chat.schemas.output import AuthorBrief
    monkeypatch.setenv("TUTOR_OW_HARNESS", "3")
    srcs = [_src(1, "Hansen"), _src(2, "Wooldridge")]

    async def fake_worker(query, thesis, author, s, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} sum", key_points=["kp"], source_ranks=[s[0].rank])

    async def fake_synth(query, sources, briefs):
        return "DEEPAGENTS SYNTHESIS TEXT"

    with patch.object(OW, "run_author_worker", side_effect=fake_worker), \
         patch("src.services.chat.agents.ow_deepagents.synthesize_with_deepagents", side_effect=fake_synth):
        ans, _ = asyncio.run(OW.run_orchestrator_workers("q", srcs, None))
    assert ans is not None and "DEEPAGENTS SYNTHESIS TEXT" in ans.definition
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -k "level2 or level3" -v`
Expected: FAIL — workflow not yet level-aware.

- [ ] **Step 3: Implement**

In `orchestrator_workers.py`, add imports near the top:

```python
from src.services.chat.agents.ow_harness import (
    maybe_traced, ow_harness_level, structured_briefs_block,
)
from src.services.chat.schemas.output import (  # extend the existing output import
    DeepTutorAnswer,  # (already imported — ensure present)
)
```

Add a helper above `run_orchestrator_workers`:

```python
def _wrap_text_answer(text: str) -> DeepTutorAnswer:
    """Wrap a free-text synthesis (level 3 deepagents) into the answer schema so
    existing callers keep working. The eval reads `.definition`."""
    return DeepTutorAnswer(tldr="", definition=text, formal_statement="",
                           example_intuition="", applications="", further_reading="")
```

Inside `run_orchestrator_workers`, right after the `briefs` list passes the `len(briefs) >= 2` guard and the `on_briefs` hook fires, insert the level branch BEFORE `plan_block = _format_plan_block(plan)`:

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
```

Then change the synthesizer user message's brief line from
`f"{_format_author_briefs(briefs)}\n\n"`
to
`f"{structured_briefs_block(briefs) if level == 2 else _format_author_briefs(briefs)}\n\n"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -v`
Expected: PASS. Regression: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -q` (level 0 default → unchanged path).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/orchestrator_workers.py src/services/chat/tests/test_ow_harness.py
git commit -m "feat(ow-harness): L2 structured handoff + L3 deepagents dispatch (flag-gated)"
```

---

## Task 4: Eval — scoped sources, content-bearing fidelity, L0/L2/L3 run

**Files:** Modify `src/services/chat/eval/ow_harness_compare.py`; Test `src/services/chat/tests/test_ow_harness.py`

- [ ] **Step 1: Write the failing test (append)**

```python
def test_owc_scoped_books_and_levels():
    assert OWC.BOOKS == ["hansen", "wooldridge", "stock_watson", "gujarati",
                         "baltagi", "pesaran", "islp", "murphy"]
    assert OWC.LEVELS == [0, 2, 3]


def test_owc_render_three_levels():
    base = {"qi": 0, "ok": True, "answer": "A", "briefs": "B", "in_tok": 1, "out_tok": 1,
            "ms": 1, "quality": {"faithfulness":4,"coverage":4,"synthesis":4,"coherence":4,"overall":4.0},
            "fidelity": 3.0}
    rows = {("L0", 0): {**base, "level": "L0"},
            ("L2", 0): {**base, "level": "L2"},
            ("L3", 0): {**base, "level": "L3"}}
    md = OWC._render_artifact(rows)
    assert "L0" in md and "L2" in md and "L3" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -k "scoped_books or three_levels" -v`
Expected: FAIL — `BOOKS` is `None`, `LEVELS` undefined.

- [ ] **Step 3: Implement**

In `ow_harness_compare.py`:

Replace `BOOKS = None  # ...` and `TOP_K = 10` region with:

```python
BOOKS = ["hansen", "wooldridge", "stock_watson", "gujarati",
         "baltagi", "pesaran", "islp", "murphy"]
TOP_K = 12
LEVELS = [0, 2, 3]  # 0 baseline, 2 structured handoff, 3 deepagents synth
_LEVEL_LABEL = {0: "L0", 2: "L2", 3: "L3"}
```

Rewrite `step_run` to loop levels, setting `TUTOR_OW_HARNESS` per level:

```python
async def step_run() -> None:
    import os
    from src.services.chat.agents.orchestrator_workers import run_orchestrator_workers
    from src.services.chat.schemas import Source

    assert _FROZEN.exists(), "run --step freeze first"
    frozen = json.loads(_FROZEN.read_text(encoding="utf-8"))
    results = _load_results()
    for level in LEVELS:
        os.environ["TUTOR_OW_HARNESS"] = str(level)
        label = _LEVEL_LABEL[level]
        for qi, q in enumerate(QUESTIONS):
            sources = [Source.model_validate_json(j) for j in frozen[str(qi)]]
            captured = {}
            t0 = time.monotonic()
            try:
                ans, _aspects = await asyncio.wait_for(
                    run_orchestrator_workers(q, sources, None,
                                             on_briefs=lambda b: captured.setdefault("briefs", b)),
                    timeout=TIMEOUT_S)
                briefs = captured.get("briefs", [])
                ok = ans is not None and len(briefs) >= 2
                results[(label, qi)] = {
                    "level": label, "qi": qi, "ok": ok,
                    "answer": _answer_text(ans), "briefs": _briefs_text(briefs),
                    "in_tok": 0, "out_tok": len(_answer_text(ans)) // 4,
                    "ms": int((time.monotonic()-t0)*1000),
                    "err": "" if ok else "no answer or <2 briefs"}
            except Exception as exc:  # noqa: BLE001
                results[(label, qi)] = {"level": label, "qi": qi, "ok": False, "answer": "",
                                        "briefs": "", "in_tok": 0, "out_tok": 0,
                                        "ms": int((time.monotonic()-t0)*1000),
                                        "err": f"{type(exc).__name__}: {exc}"}
            _save_results(results)
            print(f"[{label} Q{qi}] {'ok' if results[(label,qi)]['ok'] else 'FAILED: '+results[(label,qi)]['err']}")
    os.environ["TUTOR_OW_HARNESS"] = "0"  # restore default
```

In `step_judge`, make fidelity content-bearing: replace the fidelity block with one that filters the briefs text to content-bearing briefs is not available here (briefs are stored as text), so instead instruct the judge to ignore no-info briefs. Replace the `_FIDELITY_PROMPT` constant near the top with:

```python
_FIDELITY_PROMPT = (
    "You measure CONTEXT FIDELITY: how well the worker briefs' key facts survived "
    "into the final answer. IGNORE any brief that states the source does not discuss "
    "the topic (no-info briefs) — score only content-bearing briefs. 1-5 (5 = every "
    "content-bearing key-point is represented; 1 = most dropped). If there are no "
    "content-bearing briefs, return 0.\n"
    'Return ONLY JSON: {"fidelity":n}.'
)
```

Update the `--step` `freeze`/`run`/`judge` choices to remain the same (no new step needed).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/eval/ow_harness_compare.py src/services/chat/tests/test_ow_harness.py
git commit -m "eval(ow-harness): scoped books + content-bearing fidelity + L0/L2/L3 run"
```

---

## Task 5: Lint + full-suite gate

- [ ] **Step 1: Ruff**

Run: `.venv/bin/python -m ruff check src/services/chat/agents/ow_harness.py src/services/chat/agents/ow_deepagents.py src/services/chat/agents/orchestrator_workers.py src/services/chat/eval/ow_harness_compare.py src/services/chat/tests/test_ow_harness.py`
Expected: clean. Fix inline.

- [ ] **Step 2: Full chat suite**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: all pass (deepagents path is import-guarded, so absence is fine).

- [ ] **Step 3: Commit (only if fixes needed)**

```bash
git add -A && git commit -m "chore(ow-harness): Plan B lint + test gate green"
```

---

## Task 6: RUN the 3-way A/B (orchestrator runbook — live, deepagents installed)

> Orchestrator-run. Needs Qdrant + keys + a temporary deepagents install.

- [ ] **Step 1: Install deepagents (temporary)**

Run: `.venv/bin/python -m pip install deepagents 2>&1 | tail -3`

- [ ] **Step 2: Re-freeze scoped sources**

Run: `rm -f docs/superpowers/eval/_work_ow/results.json docs/superpowers/eval/_work_ow/frozen_sources.json && .venv/bin/python -m src.services.chat.eval.ow_harness_compare --step freeze`
Expected: each Q prints ≥ 2 distinct (now relevant) authors.

- [ ] **Step 3: Run L0/L2/L3**

Run: `.venv/bin/python -m src.services.chat.eval.ow_harness_compare --step run`
Expected: `[L0/L2/L3 Qi] ok` lines. If L3 errors on the deepagents preload API, consult the `deep-agents-memory` skill and adjust `ow_deepagents.synthesize_with_deepagents` (StoreBackend key/namespace or pass `files` in invoke state), re-run only L3. Any persistent L3 failure is recorded (non-fatal) and reported in the verdict.

- [ ] **Step 4: Judge + render**

Run: `.venv/bin/python -m src.services.chat.eval.ow_harness_compare --step judge`
Expected: `wrote .../2026-06-04-ow-harness-ablation.md`.

- [ ] **Step 5: Append the A/B verdict**

Replace the artifact's verdict section with: the re-baselined L0 numbers; **L2−L0 (structure effect)** and **L3−L2 (deepagents-agent effect)** on quality + fidelity; cost/latency (L3's agent loop will be pricier); and a keep/drop/productionize recommendation. If L3 wins, note that productionizing needs `DeepTutorAnswer`-schema integration + adding `deepagents` to `requirements.txt` (a follow-up plan).

- [ ] **Step 6: Uninstall deepagents unless L3 won**

If L3 did NOT win: `.venv/bin/python -m pip uninstall -y deepagents` (keep prod deps clean). If L3 won, leave installed and flag the requirements addition for the follow-up plan. Either way `deepagents` is NOT committed to `requirements.txt` in Plan B.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/eval/_work_ow docs/superpowers/eval/2026-06-04-ow-harness-ablation.md
git commit -m "eval(ow-harness): Plan B 3-way A/B (L0/L2/L3) run + verdict"
```

---

## Task 7: Docs lockstep

**Files:** Modify `docs/services/chat-features/36-deep-tutor.md`, `55-ow-harness-ablation.md`, `docs/system/changelog.md`

- [ ] **Step 1: Update the env row (doc 36)**

Replace the `TUTOR_OW_HARNESS` row's description with:

```
| `TUTOR_OW_HARNESS` | `0` | Orchestrator-workers harness level (doc 55): `0` baseline (flat-string briefs); `1` LangSmith tracing (observability-only); `2` structured-JSON brief handoff to the same synthesizer (no deepagents); `3` deepagents synthesizer agent (eval experiment — needs `pip install deepagents`). `>3`/junk → `0`. Never changes the answer at 0/1; any harness/level failure falls back to L0. |
```

- [ ] **Step 2: Update doc 55**

In `docs/services/chat-features/55-ow-harness-ablation.md`, update the levels table to mark L2 (structured, shipped) and L3 (deepagents, eval experiment) as implemented in Plan B, level 4 deferred; add a line pointing to the Plan B spec and the A/B artifact.

- [ ] **Step 3: Changelog**

Prepend to `docs/system/changelog.md`:

```
## 2026-06-04 — OW harness ablation Plan B (L2/L3 A/B)
Re-baselined on scoped stats/econ sources + content-bearing fidelity. Added L2
structured-JSON brief handoff (production-wired, flag-gated) and L3 deepagents
synthesizer agent (eval experiment, lazy import, not a prod dep). 3-way A/B verdict in
the ablation artifact. Level 4 (full deepagents subagents) deferred to a win.
```

- [ ] **Step 4: Commit**

```bash
git add docs/services/chat-features/36-deep-tutor.md docs/services/chat-features/55-ow-harness-ablation.md docs/system/changelog.md
git commit -m "docs(ow-harness): Plan B env row, doc 55, changelog"
```

---

## Self-Review

**Spec coverage:** scope books + re-baseline (Task 4, 6); content-bearing fidelity (Task 1 filter helper + Task 4 judge prompt); L2 structured handoff production-wired (Task 1 formatter + Task 3 wiring); L3 deepagents synthesizer eval experiment, lazy import, not in prod deps (Task 2 + Task 3 dispatch + Task 6 install/uninstall); 3-way A/B + verdict separating structure vs agent (Task 4, 6); level cap 3, level 4 deferred (Task 1); docs (Task 7). Controlled aspects (model fixed, frozen sources, caps/timeout, L0 fallback, gated deepagents) covered across Tasks 3/4/6.

**Placeholder scan:** all code concrete. The one acknowledged uncertainty — the deepagents preload API — is isolated to `ow_deepagents.synthesize_with_deepagents`, unit-tested only for its pure parts (`_brief_md`, import-error), and explicitly validated/adjusted in Task 6 against the `deep-agents-memory` skill. This is honest scoping for an external-API spike, not a placeholder in shipped/tested logic.

**Type consistency:** `AuthorBrief` fields consistent; `structured_briefs_block`/`content_bearing` names consistent (Task 1 → 3 → 4); `_wrap_text_answer` builds a valid `DeepTutorAnswer` (all required fields, text in `definition`, read by `_answer_text` which checks `definition`); `LEVELS=[0,2,3]`/`_LEVEL_LABEL` consistent with the `L0/L2/L3` row keys in `_render_artifact` and tests; `ow_harness_level()`==3 path matches `_MAX_IMPLEMENTED_LEVEL=3`.

**Known limitation:** workflow `out_tok` stays an estimate (`len//4`); L3's deepagents loop also makes internal tool-call LLM calls whose tokens the eval does not capture, so L3 USD is understated — the verdict notes L3 cost is a floor, and latency (`ms`) is the more reliable cost signal for L3.
```
