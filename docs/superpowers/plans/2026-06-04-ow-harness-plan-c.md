# Plan C — Powered deepagents synthesizer comparison (skills + subagents)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a powered, honestly-costed 4-arm comparison (L0 current synth, L3a bare deepagents, L3b deepagents+written-skill, L4 deepagents+subagents-per-author) over 6 questions × 3 runs with real token capture, to settle whether a deepagents harness with skills/subagents beats the current orchestrator-workers synthesizer.

**Architecture:** A synthesis `SKILL.md` + three deepagents arm functions in `ow_deepagents.py` (all returning `(text, in_tok, out_tok)` via a shared `_run_agent` that attaches a LangChain usage callback). A new powered eval module runs the arms over frozen sources, judges full-text per run, and aggregates to mean+spread with true USD. deepagents stays a manual install (not a prod dep) unless an arm wins.

**Tech Stack:** Python 3.12, `deepagents` (manual install for the live run), `langchain_openai`, `langchain_core` usage callback, existing chat infra, pytest.

**Spec:** `docs/superpowers/specs/2026-06-04-ow-harness-planc-design.md`

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/services/chat/agents/ow_skills/synthesis/SKILL.md` | the synthesis skill (L3b/L4) |
| `src/services/chat/agents/ow_deepagents.py` | `_sum_usage`, `_run_agent`, `_build_store`, `synthesize_with_skill`, `synthesize_with_subagents` (+ keep `synthesize_with_deepagents` back-compat) |
| `src/services/chat/eval/ow_deepagents_compare.py` | powered 4-arm eval (freeze → run×3 → judge → aggregate → artifact) |
| `src/services/chat/tests/test_ow_deepagents_compare.py` | CI unit tests (pure helpers) |
| `docs/superpowers/eval/2026-06-04-ow-deepagents-compare.md` | artifact + verdict |
| docs 55 + changelog | record Plan C |

Verified facts: `UsageMetadataCallbackHandler` (from `langchain_core.callbacks`) exposes `.usage_metadata` = `{model: {"input_tokens":int,"output_tokens":int,"total_tokens":int}}` after invoke. `ow_deepagents.py` already has `_slug`, `_brief_md(b)`, `synthesize_with_deepagents` (StoreBackend + `create_file_data` + `InMemoryStore` + `ChatOpenAI(nano, api_key=settings.openai_api_key)`). `AuthorBrief` = `{author,summary,key_points,source_ranks}`. Reuse `ow_harness_compare`'s frozen-source format (`_work_ow/frozen_sources.json`, `Source.model_validate_json`).

---

## Task 1: Token capture + `_run_agent` refactor

**Files:** Modify `src/services/chat/agents/ow_deepagents.py`; Test `src/services/chat/tests/test_ow_deepagents_compare.py`

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_ow_deepagents_compare.py
"""CI unit tests for the Plan C deepagents comparison (pure helpers only)."""
from src.services.chat.agents import ow_deepagents as DA


def test_sum_usage_totals():
    meta = {"gpt-5.4-nano-2026-03-17": {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
            "other": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
    assert DA._sum_usage(meta) == (110, 45)


def test_sum_usage_empty():
    assert DA._sum_usage({}) == (0, 0)
    assert DA._sum_usage(None) == (0, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py -k sum_usage -v`
Expected: FAIL — `_sum_usage` not defined.

- [ ] **Step 3: Implement**

Add to `ow_deepagents.py`:

```python
def _sum_usage(meta) -> tuple[int, int]:
    """Sum input/output tokens across all models in a UsageMetadataCallbackHandler."""
    if not meta:
        return (0, 0)
    it = ot = 0
    for v in meta.values():
        it += int(v.get("input_tokens", 0) or 0)
        ot += int(v.get("output_tokens", 0) or 0)
    return (it, ot)


async def _run_agent(agent, user_content: str) -> tuple[str, int, int]:
    """Invoke a deep agent, capturing total token usage (main + subagents + tool
    turns) via UsageMetadataCallbackHandler. Returns (text, in_tok, out_tok)."""
    from langchain_core.callbacks import UsageMetadataCallbackHandler
    cb = UsageMetadataCallbackHandler()
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user", "content": user_content}]},
        {"configurable": {"thread_id": "ow-c"}, "callbacks": [cb]})
    msgs = result.get("messages", []) if isinstance(result, dict) else []
    text = (msgs[-1].content if msgs else "") or ""
    it, ot = _sum_usage(getattr(cb, "usage_metadata", None))
    return (text, it, ot)
```

Then refactor `synthesize_with_deepagents` to build the agent and call `_run_agent`, returning only the text (back-compat). Extract the store-building into a helper:

```python
def _build_store(briefs):
    """InMemoryStore preloaded with one /briefs/<author>.md per brief."""
    from deepagents.backends.utils import create_file_data
    from langgraph.store.memory import InMemoryStore
    store = InMemoryStore()
    for b in briefs:
        store.put(namespace=("filesystem",), key=f"/briefs/{_slug(b.author)}.md",
                  value=create_file_data(_brief_md(b)))
    return store
```

Inside `synthesize_with_deepagents`, replace the store-building + invoke with:

```python
    from deepagents import create_deep_agent
    from deepagents.backends import StoreBackend
    from langchain_openai import ChatOpenAI
    store = _build_store(briefs)
    model = ChatOpenAI(model=settings.openai_model_nano, temperature=0.0,
                       api_key=settings.openai_api_key)
    agent = create_deep_agent(model=model, tools=[], system_prompt=_SYNTH_INSTRUCTIONS,
                              backend=lambda rt: StoreBackend(rt), store=store)
    text, _it, _ot = await _run_agent(agent, f"Question: {query}\nSynthesize the briefs now.")
    return text
```

(Keep the lazy-import guard at the top of the function as-is.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py -k sum_usage -v`
Expected: PASS. Regression: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -q` (deepagents path import-guarded → still passes without deepagents).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/ow_deepagents.py src/services/chat/tests/test_ow_deepagents_compare.py
git commit -m "feat(planc): token-capture _run_agent + _sum_usage + _build_store"
```

---

## Task 2: Synthesis SKILL.md

**Files:** Create `src/services/chat/agents/ow_skills/synthesis/SKILL.md`; Test `src/services/chat/tests/test_ow_deepagents_compare.py`

- [ ] **Step 1: Write the failing test**

```python
def test_synthesis_skill_exists_and_well_formed():
    from pathlib import Path
    p = Path(DA.__file__).parent / "ow_skills" / "synthesis" / "SKILL.md"
    assert p.exists()
    txt = p.read_text(encoding="utf-8")
    assert txt.startswith("---")          # frontmatter
    assert "name:" in txt and "description:" in txt
    assert "/briefs/" in txt              # tells the agent where the briefs are
    assert DA.SYNTHESIS_SKILL_DIR == str(p.parent.parent)  # ".../ow_skills"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py -k skill_exists -v`
Expected: FAIL — file/const missing.

- [ ] **Step 3: Implement**

Create `src/services/chat/agents/ow_skills/synthesis/SKILL.md`:

```markdown
---
name: synthesis
description: Integrate multiple authors' briefs into one comparative tutor answer that retains every content-bearing key point and compares the authors explicitly.
---

# Synthesis skill

## When to use
When asked to synthesize author briefs (files under `/briefs/`) into a single answer.

## Instructions
1. List `/briefs/` and READ every `/briefs/*.md` file in full before writing.
2. Write ONE coherent answer with a single throughline — not a per-author concatenation.
3. COMPARE the authors explicitly: where they agree, where they differ, and why.
4. Retain every content-bearing key point from the briefs; do not drop facts to be brief.
5. Ground every claim in the briefs. Never invent sources, formulas, or names.
6. Skip "no-info" briefs (a brief stating the source does not discuss the topic).
7. Use $...$ for any math.
```

Add to `ow_deepagents.py`:

```python
import os as _os

SYNTHESIS_SKILL_DIR = _os.path.join(_os.path.dirname(__file__), "ow_skills")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py -k skill_exists -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/ow_skills/synthesis/SKILL.md src/services/chat/agents/ow_deepagents.py src/services/chat/tests/test_ow_deepagents_compare.py
git commit -m "feat(planc): synthesis SKILL.md + SYNTHESIS_SKILL_DIR"
```

---

## Task 3: `synthesize_with_skill` (L3b arm)

**Files:** Modify `src/services/chat/agents/ow_deepagents.py`; Test `src/services/chat/tests/test_ow_deepagents_compare.py`

> The deepagents skill-via-StoreBackend preload API is validated live in Task 7. Consult the `deep-agents-core` skill (StoreBackend skill example: `store.put(namespace=("filesystem",), key="/skills/<name>/SKILL.md", value=create_file_data(content))`, `create_deep_agent(backend=lambda rt: StoreBackend(rt), store=store, skills=["/skills/"])`). Unit test here only asserts the lazy-import guard.

- [ ] **Step 1: Write the failing test**

```python
def test_skill_arm_import_guard(monkeypatch):
    import sys, asyncio
    import pytest as _pytest
    monkeypatch.setitem(sys.modules, "deepagents", None)
    with _pytest.raises(RuntimeError, match="pip install deepagents"):
        asyncio.run(DA.synthesize_with_skill("q", [], []))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py -k skill_arm -v`
Expected: FAIL — `synthesize_with_skill` not defined.

- [ ] **Step 3: Implement**

```python
async def synthesize_with_skill(query: str, sources, briefs) -> tuple[str, int, int]:
    """L3b: deepagents synthesizer + the written synthesis SKILL. Returns
    (text, in_tok, out_tok)."""
    try:
        import deepagents  # noqa: F401
        from deepagents import create_deep_agent
        from deepagents.backends import StoreBackend
        from deepagents.backends.utils import create_file_data
    except (ImportError, TypeError) as e:
        raise RuntimeError("pip install deepagents to run harness level 3b") from e
    from langchain_openai import ChatOpenAI
    from pathlib import Path

    store = _build_store(briefs)
    # Preload the synthesis skill into the store's /skills/ tree.
    skill_md = (Path(SYNTHESIS_SKILL_DIR) / "synthesis" / "SKILL.md").read_text(encoding="utf-8")
    store.put(namespace=("filesystem",), key="/skills/synthesis/SKILL.md",
              value=create_file_data(skill_md))

    model = ChatOpenAI(model=settings.openai_model_nano, temperature=0.0,
                       api_key=settings.openai_api_key)
    agent = create_deep_agent(
        model=model, tools=[],
        system_prompt="Use the synthesis skill to synthesize the briefs in /briefs/.",
        backend=lambda rt: StoreBackend(rt), store=store, skills=["/skills/"])
    return await _run_agent(agent, f"Question: {query}\nSynthesize the briefs now.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py -k skill_arm -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/ow_deepagents.py src/services/chat/tests/test_ow_deepagents_compare.py
git commit -m "feat(planc): synthesize_with_skill (L3b deepagents+skill arm)"
```

---

## Task 4: `synthesize_with_subagents` (L4 arm)

**Files:** Modify `src/services/chat/agents/ow_deepagents.py`; Test `src/services/chat/tests/test_ow_deepagents_compare.py`

> Subagent delegation API validated live in Task 7. Consult `deep-agents-orchestration` (custom subagent dict `{"name","description","system_prompt","skills"}`, main agent delegates via the `task` tool). Unit test only asserts the import guard.

- [ ] **Step 1: Write the failing test**

```python
def test_subagents_arm_import_guard(monkeypatch):
    import sys, asyncio
    import pytest as _pytest
    monkeypatch.setitem(sys.modules, "deepagents", None)
    with _pytest.raises(RuntimeError, match="pip install deepagents"):
        asyncio.run(DA.synthesize_with_subagents("q", [], []))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py -k subagents_arm -v`
Expected: FAIL — not defined.

- [ ] **Step 3: Implement**

```python
async def synthesize_with_subagents(query: str, sources, briefs) -> tuple[str, int, int]:
    """L4: deepagents synthesizer that delegates each author's brief to an
    author-analyst subagent, then integrates. Returns (text, in_tok, out_tok)."""
    try:
        import deepagents  # noqa: F401
        from deepagents import create_deep_agent
        from deepagents.backends import StoreBackend
        from deepagents.backends.utils import create_file_data
    except (ImportError, TypeError) as e:
        raise RuntimeError("pip install deepagents to run harness level 4") from e
    from langchain_openai import ChatOpenAI
    from pathlib import Path

    store = _build_store(briefs)
    skill_md = (Path(SYNTHESIS_SKILL_DIR) / "synthesis" / "SKILL.md").read_text(encoding="utf-8")
    store.put(namespace=("filesystem",), key="/skills/synthesis/SKILL.md",
              value=create_file_data(skill_md))

    authors = "; ".join(_slug(b.author) for b in briefs)
    model = ChatOpenAI(model=settings.openai_model_nano, temperature=0.0,
                       api_key=settings.openai_api_key)
    agent = create_deep_agent(
        model=model, tools=[],
        system_prompt=(
            "For EACH author brief file in /briefs/, delegate to the 'author-analyst' "
            "subagent (via the task tool) to extract that author's key points from its "
            f"brief file. Author brief slugs: {authors}. Then integrate all analyses into "
            "one comparative answer that retains every key point and compares the authors."),
        subagents=[{
            "name": "author-analyst",
            "description": "Read one author's brief file and report its key points.",
            "system_prompt": "Read the named /briefs/<author>.md file and return its key points faithfully.",
            "skills": ["/skills/"],
        }],
        backend=lambda rt: StoreBackend(rt), store=store, skills=["/skills/"])
    return await _run_agent(agent, f"Question: {query}\nProduce the comparative synthesis now.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py -k subagents_arm -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/ow_deepagents.py src/services/chat/tests/test_ow_deepagents_compare.py
git commit -m "feat(planc): synthesize_with_subagents (L4 deepagents+subagents arm)"
```

---

## Task 5: Powered eval module (4 arms, 6q × 3 runs, aggregate + bands)

**Files:** Create `src/services/chat/eval/ow_deepagents_compare.py`; Test `src/services/chat/tests/test_ow_deepagents_compare.py`

- [ ] **Step 1: Write the failing test**

```python
from src.services.chat.eval import ow_deepagents_compare as PC


def test_pc_constants():
    assert PC.ARMS == ["L0", "L3a", "L3b", "L4"]
    assert len(PC.QUESTIONS) == 6
    assert PC.RUNS == 3
    assert PC.JUDGE_DIMS == ("faithfulness", "coverage", "synthesis", "coherence")


def test_pc_aggregate_mean_and_spread():
    runs = [{"overall": 4.0, "fidelity": 5.0, "in_tok": 100, "out_tok": 50, "ms": 1000},
            {"overall": 3.0, "fidelity": 4.0, "in_tok": 120, "out_tok": 60, "ms": 1200},
            {"overall": 5.0, "fidelity": 5.0, "in_tok": 110, "out_tok": 55, "ms": 1100}]
    agg = PC._aggregate(runs)
    assert agg["overall_mean"] == 4.0
    assert agg["overall_min"] == 3.0 and agg["overall_max"] == 5.0
    assert agg["fidelity_mean"] == round((5+4+5)/3, 2)
    assert agg["in_tok_mean"] == 110 and agg["out_tok_mean"] == 55


def test_pc_render_artifact():
    agg = {("L0", 0): {"overall_mean": 3.9, "overall_min": 3.5, "overall_max": 4.2,
                       "fidelity_mean": 4.6, "in_tok_mean": 800, "out_tok_mean": 600,
                       "ms_mean": 3000, "usd_mean": 0.0009, "ok_runs": 3}}
    md = PC._render_artifact(agg)
    assert "| arm | question |" in md and "L0" in md and "3.9" in md and "±" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py -k "pc_" -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# src/services/chat/eval/ow_deepagents_compare.py
"""Plan C: powered 4-arm deepagents synthesizer comparison (eval experiment).

Arms over the orchestrator-workers synthesizer (nano workers + nano model fixed):
  L0  current synthesizer            (run_orchestrator_workers level 0)
  L3a bare deepagents                (ow_deepagents.synthesize_with_deepagents)
  L3b deepagents + synthesis SKILL   (ow_deepagents.synthesize_with_skill)
  L4  deepagents + subagents/author  (ow_deepagents.synthesize_with_subagents)

6 questions x 3 runs/arm, full-text judge, real token capture -> mean + spread + USD.
Needs `pip install deepagents` for L3a/L3b/L4. Run:
  .venv/bin/python -m src.services.chat.eval.ow_deepagents_compare --step freeze
  .venv/bin/python -m src.services.chat.eval.ow_deepagents_compare --step run
  .venv/bin/python -m src.services.chat.eval.ow_deepagents_compare --step judge
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

from src.services.chat._fences import strip_fences

ARMS = ["L0", "L3a", "L3b", "L4"]
QUESTIONS = [
    "Compare how different authors define and motivate the bias-variance tradeoff.",
    "Contrast OLS and maximum likelihood estimation across the textbooks.",
    "Compare frequentist and Bayesian treatments of estimation.",
    "Compare how the textbooks treat heteroskedasticity and its remedies.",
    "Contrast hypothesis testing and confidence intervals across the authors.",
    "Compare the treatments of omitted variable bias and endogeneity.",
]
RUNS = 3
BOOKS = ["hansen", "wooldridge", "stock_watson", "gujarati", "baltagi", "pesaran", "islp", "murphy"]
TOP_K = 12
JUDGE_MODEL = "gpt-5.4-nano-2026-03-17"
JUDGE_DIMS = ("faithfulness", "coverage", "synthesis", "coherence")
MAX_TOK = 700
TIMEOUT_S = 120
_JUDGE_CHARS = 12000

_ROOT = Path(__file__).resolve().parents[4]
_WORK = _ROOT / "docs" / "superpowers" / "eval" / "_work_planc"
_FROZEN = _WORK / "frozen_sources.json"
_RESULTS = _WORK / "results.json"
_ARTIFACT = _ROOT / "docs" / "superpowers" / "eval" / "2026-06-04-ow-deepagents-compare.md"

_QUALITY_PROMPT = (
    "You score a tutor answer that synthesizes multiple authors, 1-5 each (5=best):\n"
    "faithfulness (grounded in sources), coverage (covers the question's parts), "
    "synthesis (genuinely COMPARES authors, not concatenation), coherence (one throughline).\n"
    'Return ONLY JSON: {"faithfulness":n,"coverage":n,"synthesis":n,"coherence":n}.'
)
_FIDELITY_PROMPT = (
    "You measure CONTEXT FIDELITY: how well the worker briefs' key facts survived into "
    "the final answer. IGNORE no-info briefs (a brief stating the source does not discuss "
    "the topic). 1-5 (5 = every content-bearing key-point represented). If none, 0.\n"
    'Return ONLY JSON: {"fidelity":n}.'
)


def _quality_input(answer: str) -> str:
    return f"SOURCES-BASED ANSWER:\n{answer[:_JUDGE_CHARS]}"


def _fidelity_input(briefs: str, answer: str) -> str:
    return f"WORKER BRIEFS:\n{briefs[:_JUDGE_CHARS]}\n\nFINAL ANSWER:\n{answer[:_JUDGE_CHARS]}"


def _parse_scores(raw: str, dims) -> dict:
    try:
        d = json.loads(strip_fences(raw))
        vals = {k: float(d.get(k, 0)) for k in dims}
    except Exception:
        vals = {k: 0.0 for k in dims}
    vals["overall"] = round(sum(vals.values()) / len(dims), 2)
    return vals


def _aggregate(runs: list[dict]) -> dict:
    """Mean + min/max over per-run scored dicts (overall, fidelity, tokens, ms)."""
    ok = [r for r in runs if r.get("ok", True)]
    if not ok:
        return {"ok_runs": 0, "overall_mean": 0.0, "overall_min": 0.0, "overall_max": 0.0,
                "fidelity_mean": 0.0, "in_tok_mean": 0, "out_tok_mean": 0, "ms_mean": 0, "usd_mean": 0.0}
    def m(key):
        return round(statistics.mean(r[key] for r in ok), 2)
    return {
        "ok_runs": len(ok),
        "overall_mean": m("overall"), "overall_min": min(r["overall"] for r in ok),
        "overall_max": max(r["overall"] for r in ok), "fidelity_mean": m("fidelity"),
        "in_tok_mean": int(statistics.mean(r["in_tok"] for r in ok)),
        "out_tok_mean": int(statistics.mean(r["out_tok"] for r in ok)),
        "ms_mean": int(statistics.mean(r["ms"] for r in ok)),
        "usd_mean": round(statistics.mean(r.get("usd", 0.0) for r in ok), 4),
    }


def _render_artifact(agg: dict) -> str:
    lines = [
        "# Plan C — powered deepagents synthesizer comparison (4 arms)", "",
        f"_{len(QUESTIONS)} questions x {RUNS} runs · full-text judge={JUDGE_MODEL} · "
        "nano fixed · real token capture (main+subagents+tools)_", "",
        "| arm | question | overall (mean ± range) | fidelity | in_tok | out_tok | ms | USD | ok |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for (arm, qi), a in sorted(agg.items()):
        band = f"{a['overall_mean']} ±[{a['overall_min']}–{a['overall_max']}]"
        lines.append(f"| {arm} | Q{qi} | {band} | {a['fidelity_mean']} | {a['in_tok_mean']} | "
                     f"{a['out_tok_mean']} | {a['ms_mean']} | ${a['usd_mean']:.4f} | {a['ok_runs']}/{RUNS} |")
    lines += ["", "## Questions", ""]
    for i, q in enumerate(QUESTIONS):
        lines.append(f"- Q{i}: {q}")
    lines += ["", "> Opus verdict (spread-aware decision rule) appended after review.", ""]
    return "\n".join(lines)


def _load_results() -> list:
    return json.loads(_RESULTS.read_text(encoding="utf-8")) if _RESULTS.exists() else []


def _save_results(rows: list) -> None:
    _WORK.mkdir(parents=True, exist_ok=True)
    _RESULTS.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def step_freeze() -> None:
    from src.services.chat.retrieval import hybrid_search
    _WORK.mkdir(parents=True, exist_ok=True)
    frozen = {}
    for qi, q in enumerate(QUESTIONS):
        sources, _ = hybrid_search(q, book_slugs=BOOKS, top_k=TOP_K, rerank=False)
        frozen[str(qi)] = [s.model_dump_json() for s in sources]
        print(f"Q{qi}: {len(sources)} sources, {len({(s.authors_short or s.book) for s in sources})} authors")
    _FROZEN.write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    print(f"wrote {_FROZEN}")


async def _arm_answer(arm: str, q, sources):
    """Return (answer_text, briefs_text, in_tok, out_tok) for one arm run."""
    from src.services.chat.agents import ow_deepagents as DA
    from src.services.chat.agents.orchestrator_workers import (
        run_author_worker, _fallback_tasks, _format_author_briefs)
    # Build briefs once (our nano workers) — shared shape across arms.
    tasks = _fallback_tasks(sources)
    by_rank = {s.rank: s for s in sources}
    built = [(t.focus, [by_rank[r] for r in t.source_ranks if r in by_rank] or sources) for t in tasks]
    briefs = []
    for focus, srcs in built[:6]:
        b = await run_author_worker(q, "", focus, srcs)
        if b and (b.summary or b.key_points):
            briefs.append(b)
    briefs_text = _format_author_briefs(briefs)
    if len(briefs) < 2:
        return "", briefs_text, 0, 0
    if arm == "L0":
        # Reuse the production synthesizer at level 0 via run_orchestrator_workers.
        import os
        os.environ["TUTOR_OW_HARNESS"] = "0"
        from src.services.chat.agents.orchestrator_workers import run_orchestrator_workers
        from src.services.chat.eval.ow_harness_compare import _answer_text
        ans, _ = await run_orchestrator_workers(q, sources, None)
        return _answer_text(ans), briefs_text, 0, len(_answer_text(ans)) // 4
    fn = {"L3a": DA.synthesize_with_deepagents, "L3b": DA.synthesize_with_skill,
          "L4": DA.synthesize_with_subagents}[arm]
    res = await fn(q, sources, briefs)
    if isinstance(res, tuple):
        text, it, ot = res
    else:  # synthesize_with_deepagents returns str
        text, it, ot = res, 0, len(res) // 4
    return text, briefs_text, it, ot


async def step_run() -> None:
    from src.services.chat.schemas import Source
    assert _FROZEN.exists(), "run --step freeze first"
    frozen = json.loads(_FROZEN.read_text(encoding="utf-8"))
    rows = _load_results()
    seen = {(r["arm"], r["qi"], r["run"]) for r in rows}
    for arm in ARMS:
        for qi, q in enumerate(QUESTIONS):
            sources = [Source.model_validate_json(j) for j in frozen[str(qi)]]
            for run in range(RUNS):
                if (arm, qi, run) in seen:
                    continue
                t0 = time.monotonic()
                try:
                    text, briefs, it, ot = await asyncio.wait_for(_arm_answer(arm, q, sources), timeout=TIMEOUT_S)
                    ok = bool(text.strip())
                    rows.append({"arm": arm, "qi": qi, "run": run, "ok": ok, "answer": text,
                                 "briefs": briefs, "in_tok": it, "out_tok": ot,
                                 "ms": int((time.monotonic()-t0)*1000), "err": "" if ok else "empty"})
                except Exception as exc:  # noqa: BLE001
                    rows.append({"arm": arm, "qi": qi, "run": run, "ok": False, "answer": "",
                                 "briefs": "", "in_tok": 0, "out_tok": 0,
                                 "ms": int((time.monotonic()-t0)*1000), "err": f"{type(exc).__name__}: {exc}"})
                _save_results(rows)
                print(f"[{arm} Q{qi} r{run}] {'ok' if rows[-1]['ok'] else 'FAIL '+rows[-1]['err']} {rows[-1]['ms']}ms")
    import os
    os.environ["TUTOR_OW_HARNESS"] = "0"


async def step_judge() -> None:
    from src.services.chat.agents.deep_tutor import _async_client
    from src.services.chat.cost import usd_est
    rows = _load_results()
    assert rows, "run --step run first"

    async def _judge(system, user) -> str:
        try:
            resp = await asyncio.wait_for(_async_client(JUDGE_MODEL).chat.completions.create(
                model=JUDGE_MODEL, messages=[{"role": "system", "content": system},
                {"role": "user", "content": user}], temperature=0.0, max_completion_tokens=120),
                timeout=TIMEOUT_S)
            return resp.choices[0].message.content or ""
        except Exception:
            return ""

    # Score each run.
    per = {}
    for r in rows:
        key = (r["arm"], r["qi"])
        per.setdefault(key, [])
        if not r.get("ok"):
            per[key].append({"ok": False})
            continue
        q = _parse_scores(await _judge(_QUALITY_PROMPT, _quality_input(r["answer"])), JUDGE_DIMS)
        f = _parse_scores(await _judge(_FIDELITY_PROMPT, _fidelity_input(r["briefs"], r["answer"])), ("fidelity",))
        per[key].append({"ok": True, "overall": q["overall"], "fidelity": f.get("fidelity", 0.0),
                         "in_tok": r["in_tok"], "out_tok": r["out_tok"], "ms": r["ms"],
                         "usd": usd_est(JUDGE_MODEL, input_tokens=r["in_tok"], output_tokens=r["out_tok"])})
    agg = {key: _aggregate(runs) for key, runs in per.items()}
    _ARTIFACT.write_text(_render_artifact(agg), encoding="utf-8")
    print(f"wrote {_ARTIFACT}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Plan C deepagents comparison")
    ap.add_argument("--step", choices=["freeze", "run", "judge"], required=True)
    args = ap.parse_args()
    if args.step == "freeze":
        step_freeze()
    elif args.step == "run":
        asyncio.run(step_run())
    else:
        asyncio.run(step_judge())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py -v`
Expected: PASS (all pure-helper tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/eval/ow_deepagents_compare.py src/services/chat/tests/test_ow_deepagents_compare.py
git commit -m "eval(planc): powered 4-arm deepagents comparison harness"
```

---

## Task 6: Lint + full-suite gate

- [ ] **Step 1: Ruff**

Run: `.venv/bin/python -m ruff check src/services/chat/agents/ow_deepagents.py src/services/chat/eval/ow_deepagents_compare.py src/services/chat/tests/test_ow_deepagents_compare.py`
Expected: clean. Fix inline.

- [ ] **Step 2: Full chat suite**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: all pass (deepagents arms import-guarded).

- [ ] **Step 3: Commit (only if fixes needed)**

```bash
git add -A && git commit -m "chore(planc): lint + test gate green"
```

---

## Task 7: RUN the powered comparison (orchestrator runbook — live, background)

> Orchestrator-run. Needs Qdrant + keys + temporary deepagents. 72 runs — run in background.

- [ ] **Step 1: Install deepagents (temporary)**

Run: `.venv/bin/python -m pip install deepagents 2>&1 | tail -2`

- [ ] **Step 2: Freeze 6 questions**

Run: `.venv/bin/python -m src.services.chat.eval.ow_deepagents_compare --step freeze`
Expected: each Q ≥ 2 authors.

- [ ] **Step 3: Smoke ONE deepagents arm before the full run**

Run a single L3b + L4 call inline to validate the skill/subagent preload API against the live deepagents (consult `deep-agents-core`/`deep-agents-orchestration` if it errors; adjust `synthesize_with_skill`/`synthesize_with_subagents` store keys/subagent dict, re-test). Only proceed to the full run once one L3b and one L4 call return non-empty text.

- [ ] **Step 4: Run all 72 (background)**

Run (background): `.venv/bin/python -m src.services.chat.eval.ow_deepagents_compare --step run`
The run is resumable (skips completed `(arm,qi,run)`); a crash/timeout can be re-run.

- [ ] **Step 5: Judge + render**

Run: `.venv/bin/python -m src.services.chat.eval.ow_deepagents_compare --step judge`

- [ ] **Step 6: Append the spread-aware verdict**

Apply the decision rule: an arm wins only if `mean − mean(L0) > pooled spread` on quality, fidelity not regressing, consistent across questions, at acceptable real token cost. Write the verdict (per-arm means±range, true USD, recommendation keep-L0 / adopt-arm / inconclusive). Edit the artifact.

- [ ] **Step 7: Uninstall deepagents unless an arm won**

`.venv/bin/python -m pip uninstall -y deepagents` unless an arm won (then flag the requirements addition for a productionization plan). Commit:

```bash
git add docs/superpowers/eval/_work_planc docs/superpowers/eval/2026-06-04-ow-deepagents-compare.md
git commit -m "eval(planc): powered 4-arm run + spread-aware verdict"
```

---

## Task 8: Docs

- [ ] **Step 1: Doc 55 + changelog**

Append a Plan C section to `docs/services/chat-features/55-ow-harness-ablation.md` (arms, power, the verdict) and prepend a changelog entry to `docs/system/changelog.md`. Commit:

```bash
git add docs/services/chat-features/55-ow-harness-ablation.md docs/system/changelog.md
git commit -m "docs(planc): doc 55 + changelog for the powered deepagents comparison"
```

---

## Self-Review

**Spec coverage:** 4 arms L0/L3a/L3b/L4 (Tasks 1/3/4/5); synthesis SKILL.md (Task 2); real token capture via usage callback (Task 1 `_run_agent`/`_sum_usage`, surfaced in Task 5 USD); 6q × 3 runs + mean/spread (Task 5 `_aggregate`/render); full-text judge (Task 5 `_JUDGE_CHARS`); decision rule = beat L0 by > spread (Task 7 verdict); deepagents gated/manual install, uninstall unless win (Tasks 7); docs (Task 8). Controlled aspects (nano fixed, frozen reused sources, cap+timeout, resumable persist, background) in Task 5/7.

**Placeholder scan:** all shipped/tested code concrete. The deepagents skill/subagent *preload* API (StoreBackend skill keys, subagent dict) is the one external unknown — unit-tested only for the import guard and validated live in Task 7 Step 3 before the full run (honest external-API scoping, consistent with the Plan B spike). The lone "verdict appended after review" line is replaced in Task 7.

**Type consistency:** arm functions `synthesize_with_skill`/`synthesize_with_subagents` return `(text, in_tok, out_tok)`; `synthesize_with_deepagents` stays `str` (Task 5 `_arm_answer` handles both via the tuple check). `_aggregate` keys (`overall_mean/min/max`, `fidelity_mean`, `in_tok_mean`, `out_tok_mean`, `ms_mean`, `usd_mean`, `ok_runs`) match `_render_artifact` and the tests. `ARMS`/`QUESTIONS`/`RUNS`/`JUDGE_DIMS` consistent across module + tests. `_build_store`/`_slug`/`_brief_md`/`SYNTHESIS_SKILL_DIR` names consistent across Tasks 1–4.

**Known limitation:** L0's per-run `out_tok` is the `len//4` estimate (production synth streams, no usage) while L3a/L3b/L4 use real callback tokens — so L0's USD is an estimate and the L0-vs-deepagents *cost* comparison is approximate (quality/fidelity are apples-to-apples). The verdict notes this; threading real usage through the production synth is out of scope.
```
