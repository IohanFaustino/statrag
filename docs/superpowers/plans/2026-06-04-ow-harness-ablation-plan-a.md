# Orchestrator-Workers Harness Ablation — Plan A (spike + L0/L1 + baseline eval)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the orchestrator-workers harness ablation's foundation — a deepagents feasibility spike (go/no-go gate for L2/L3), the reusable eval-flow methodology doc, the L0/L1 harness scaffold (flag + LangSmith tracing passthrough + a brief-capture hook), and a baseline eval that scores L0 quality + the context-fidelity metric. L2/L3 deepagents conversion is **Plan B**, written only after the spike confirms feasibility.

**Architecture:** Add a thin `ow_harness.py` (flag reader + LangSmith tracing passthrough) and a non-invasive `on_briefs` capture hook to `run_orchestrator_workers`; leave the workflow's behavior identical (L0 == current; L1 == L0 + tracing). A new eval module runs the workflow over frozen multi-author sources and judges quality + context-fidelity. Everything is flag-gated and falls back to L0; deepagents is **not** touched in Plan A beyond the throwaway spike.

**Tech Stack:** Python 3.12, existing chat infra (`run_orchestrator_workers`, `hybrid_search`, `_async_client`, `usd_est`, `strip_fences`), `langsmith>=0.3` (already a dep), pytest. deepagents only in the spike venv.

**Spec:** `docs/superpowers/specs/2026-06-04-orchestrator-workers-harness-ablation-design.md`

---

## File Structure

| Path | Responsibility |
|---|---|
| `scripts/spike_deepagents.py` | throwaway feasibility spike (Task 1) |
| `docs/superpowers/eval/_spike/deepagents-findings.md` | spike findings (Task 1) |
| `docs/services/chat-features/eval-methodology.md` | reusable prepare→levels→compare→verdict playbook (Task 2) |
| `src/services/chat/agents/orchestrator_workers.py` | `on_briefs` capture hook (Task 3) |
| `src/services/chat/agents/ow_harness.py` | `ow_harness_level()` + `maybe_traced()` (Task 4) |
| `src/services/chat/eval/ow_harness_compare.py` | baseline eval (Task 5) |
| `src/services/chat/tests/test_ow_harness.py` | CI tests: hook, level parse, tracing passthrough, eval helpers (Tasks 3–5) |
| `docs/services/chat-features/55-ow-harness-ablation.md`, `36-deep-tutor.md`, `docs/system/{invariants,changelog}.md` | docs (Task 8) |
| `docs/superpowers/eval/2026-06-04-ow-harness-ablation.md` | baseline artifact (Task 7) |

Key existing facts (verified): `run_orchestrator_workers(query, sources, plan, *, orchestrator_model=None, worker_model=None, synth_model=None, figures=None, on_aspect_delta=None) -> tuple[DeepTutorAnswer | None, dict[str,str]]` in `orchestrator_workers.py`; it computes `briefs: list[AuthorBrief]` then calls `_format_author_briefs(briefs)`. `AuthorBrief` = `{author:str, summary:str, key_points:list[str], source_ranks:list[int]}`. `Source` is a pydantic model (`model_dump_json` / `model_validate_json`). `hybrid_search(query, *, book_slugs=None, top_k=5, rerank=False) -> (list[Source], meta)`.

---

## Task 1: deepagents feasibility spike (GATE — orchestrator-run)

> Run by the orchestrator (needs `pip install` + judgment), not a subagent. This gates Plan B; Plan A proceeds regardless.

**Files:** Create `scripts/spike_deepagents.py`, `docs/superpowers/eval/_spike/deepagents-findings.md`

- [ ] **Step 1: Install deepagents into the venv**

Run: `.venv/bin/python -m pip install deepagents 2>&1 | tail -5`
Expected: a successful install (note the resolved version + whether it forced a langgraph/langchain change). If it conflicts with the pinned `langgraph>=1.0,<2.0`, STOP and record the conflict in the findings doc — that is itself the feasibility verdict (deepagents incompatible → L2/L3 blocked).

- [ ] **Step 2: Write the spike script**

Consult the `deep-agents-core` and `deep-agents-orchestration` skills for the current API before writing. The spike must answer: (a) does `create_deep_agent` (or the current entrypoint) import + run on this stack; (b) can it be driven by an OpenAI-compatible model pointing at our router (base_url/key), or only by LangChain `ChatModel` objects; (c) what does the shared virtual-filesystem/state API look like for a worker→synthesizer handoff.

```python
# scripts/spike_deepagents.py  (throwaway — not committed to prod deps)
"""Feasibility spike: can deepagents run on our stack and drive our models?
Builds a trivial 2-subagent example that writes/reads a shared file, using an
OpenAI-compatible model aimed at the project's router. Prints findings."""
from __future__ import annotations
import os, traceback

def main() -> None:
    findings = []
    try:
        import deepagents  # noqa: F401
        findings.append(f"import deepagents OK (version={getattr(deepagents,'__version__','?')})")
    except Exception as e:
        findings.append(f"IMPORT FAILED: {type(e).__name__}: {e}")
        print("\n".join(findings)); return
    # Drive with an OpenAI-compatible model via langchain-openai pointed at our key.
    try:
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(model="gpt-5.4-nano-2026-03-17", temperature=0,
                           api_key=os.environ.get("OPENAI_API_KEY"))
        findings.append("ChatOpenAI(nano) constructed OK")
    except Exception as e:
        findings.append(f"model construct FAILED: {type(e).__name__}: {e}")
    # Build a minimal deep agent with a subagent + filesystem, per the skill's API.
    try:
        from deepagents import create_deep_agent  # API per deep-agents-core skill
        agent = create_deep_agent(
            tools=[], model=model,
            instructions="Write 'hello from worker' to file brief.txt, then read it back.",
        )
        result = agent.invoke({"messages": [{"role": "user", "content": "do it"}]})
        findings.append(f"agent.invoke OK; result keys={list(result)[:6]}")
    except Exception as e:
        findings.append(f"agent run FAILED: {type(e).__name__}: {e}\n{traceback.format_exc()[:600]}")
    print("\n".join(findings))

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the spike + record findings**

Run: `.venv/bin/python scripts/spike_deepagents.py 2>&1 | tail -30`
Then write `docs/superpowers/eval/_spike/deepagents-findings.md` capturing: resolved version, dependency-conflict status, whether the OpenAI-compat model drove the agent, the filesystem/state API shape, and a **verdict line**: `FEASIBLE` (Plan B can proceed) or `BLOCKED: <reason>` (stop at L1). Then `.venv/bin/python -m pip uninstall -y deepagents` to keep the venv clean for the rest of Plan A (re-installed in Plan B if FEASIBLE).

- [ ] **Step 4: Commit (script + findings)**

```bash
git add scripts/spike_deepagents.py docs/superpowers/eval/_spike/deepagents-findings.md
git commit -m "spike(ow-harness): deepagents feasibility probe + findings"
```

---

## Task 2: Eval-flow methodology playbook

**Files:** Create `docs/services/chat-features/eval-methodology.md`

- [ ] **Step 1: Write the playbook**

Create `docs/services/chat-features/eval-methodology.md` documenting the reusable flow distilled from the ts-components and planner-chain evals:

```markdown
# Eval-flow methodology — prepare → compare → verdict

Reusable recipe for comparing models/harness-levels on a single pipeline stage.

## 1. Prepare (freeze inputs)
- Pick a small FIXED question set sized to the stage (e.g. fan-out questions for
  orchestrator-workers, which only fires at ≥2 authors).
- Retrieve sources ONCE per question and freeze them to disk. Every contestant
  sees identical inputs → differences are the variable under test, not retrieval.

## 2. Compare (run contestants)
- One contestant = one (model | harness-level). Hold all other axes constant so
  the result is interpretable (isolate one variable).
- Hard `max_completion_tokens` cap + per-call `asyncio.wait_for` timeout. Persist
  each result immediately (a crash loses nothing).
- Parse model output as FREE TEXT + `strip_fences` where possible: avoids the
  qwen `json_schema` hang and gemini trailing-comma failures (both on record).
- try/except per contestant → record FAILED, never crash the sweep.

## 3. Judge + verdict
- Fixed judge model (nano) + a gold anchor; score 1–5 on stage-specific dims.
- Capture USD (`usd_est` from real `resp.usage`), latency, tokens.
- Emit ONE markdown artifact: score table + raw outputs + a human (Opus) verdict
  that calls out judge artifacts (e.g. uniform conciseness scores carry no signal)
  and whether the added cost/complexity earns its place.

## Known model quirks (design around them)
- qwen-plus: hangs under `response_format=json_schema` → free-text + parse.
- gemini-2.5-flash: emits non-strict JSON (trailing commas) → free-text + lenient parse.
- nano (reasoning): needs generous token budgets or it truncates JSON mid-string.

## Examples in repo
- `src/services/chat/eval/ts_components_compare.py`
- `src/services/chat/eval/planner_chain_compare.py`
- `src/services/chat/eval/ow_harness_compare.py`
```

- [ ] **Step 2: Commit**

```bash
git add docs/services/chat-features/eval-methodology.md
git commit -m "docs(eval): reusable prepare->compare->verdict methodology playbook"
```

---

## Task 3: `on_briefs` capture hook in orchestrator-workers

**Files:** Modify `src/services/chat/agents/orchestrator_workers.py`; Test `src/services/chat/tests/test_ow_harness.py`

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_ow_harness.py
"""Tests for the orchestrator-workers harness scaffold + eval helpers."""
import asyncio
from unittest.mock import patch
from src.services.chat.agents import orchestrator_workers as OW
from src.services.chat.schemas.output import AuthorBrief
from src.services.chat.schemas import Source


def _src(rank, author):
    return Source(rank=rank, book="b", chapter="c", section="s", title="t",
                  excerpt="", score=1.0, chunkId=f"x{rank}", chunk="text",
                  authors_short=author)


def test_on_briefs_hook_receives_briefs():
    captured = {}
    srcs = [_src(1, "Hansen"), _src(2, "Wooldridge")]

    async def fake_worker(query, thesis, author, s, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} summary",
                           key_points=[f"{author} kp"], source_ranks=[s[0].rank])

    async def fake_stream(*a, **k):
        from src.services.chat.schemas.output import DeepTutorAnswer
        return DeepTutorAnswer(), {}

    with patch.object(OW, "run_author_worker", side_effect=fake_worker), \
         patch.object(OW, "_stream_structured", side_effect=fake_stream):
        OW.run_orchestrator_workers  # ensure symbol exists
        ans, _ = asyncio.run(OW.run_orchestrator_workers(
            "q", srcs, None, on_briefs=lambda b: captured.setdefault("briefs", b)))
    assert "briefs" in captured
    assert {b.author for b in captured["briefs"]} == {"Hansen", "Wooldridge"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py::test_on_briefs_hook_receives_briefs -v`
Expected: FAIL — `run_orchestrator_workers` has no `on_briefs` parameter (TypeError).

- [ ] **Step 3: Add the hook**

In `run_orchestrator_workers`, add `on_briefs=None` to the signature (after `on_aspect_delta=None`). Immediately after the line that builds `briefs` and confirms `len(briefs) >= 2` (just before `plan_block = _format_plan_block(plan)`), insert:

```python
    if on_briefs is not None:
        try:
            on_briefs(briefs)
        except Exception:  # noqa: BLE001  (a capture hook must never break drafting)
            logger.exception("on_briefs hook failed; continuing")
```

Update the docstring to mention `on_briefs` (called with the worker briefs before synthesis; best-effort, for eval/observability).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -v`
Expected: PASS. Also run `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -q` → no regression.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/orchestrator_workers.py src/services/chat/tests/test_ow_harness.py
git commit -m "feat(ow-harness): non-invasive on_briefs capture hook"
```

---

## Task 4: `ow_harness.py` — level flag + LangSmith tracing passthrough (L0/L1)

**Files:** Create `src/services/chat/agents/ow_harness.py`; Test `src/services/chat/tests/test_ow_harness.py`

- [ ] **Step 1: Write the failing test (append)**

```python
from src.services.chat.agents import ow_harness as H


def test_level_parse_default_and_clamp(monkeypatch):
    monkeypatch.delenv("TUTOR_OW_HARNESS", raising=False)
    assert H.ow_harness_level() == 0
    monkeypatch.setenv("TUTOR_OW_HARNESS", "2")
    assert H.ow_harness_level() == 2
    monkeypatch.setenv("TUTOR_OW_HARNESS", "9")
    assert H.ow_harness_level() == 0   # out of range -> safe default
    monkeypatch.setenv("TUTOR_OW_HARNESS", "junk")
    assert H.ow_harness_level() == 0


def test_maybe_traced_is_passthrough_when_off(monkeypatch):
    monkeypatch.delenv("TUTOR_OW_HARNESS", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    def f(x):
        return x + 1

    wrapped = H.maybe_traced(f, name="f")
    assert wrapped is f or wrapped(1) == 2   # no-op or behavior-identical


def test_maybe_traced_preserves_behavior_when_on(monkeypatch):
    monkeypatch.setenv("TUTOR_OW_HARNESS", "1")
    monkeypatch.setenv("LANGSMITH_API_KEY", "fake")

    def f(x):
        return x * 3

    wrapped = H.maybe_traced(f, name="f")
    assert wrapped(2) == 6   # tracing must never change the result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -k "level or maybe_traced" -v`
Expected: FAIL — module `ow_harness` not found.

- [ ] **Step 3: Implement**

```python
# src/services/chat/agents/ow_harness.py
"""Harness-level scaffold for the orchestrator-workers stage (ablation pilot).

TUTOR_OW_HARNESS selects the level:
  0 = baseline (current behavior, no harness) — default and fallback
  1 = observability (LangSmith tracing; behavior identical)
  2 = structured context via deepagents shared FS   (Plan B)
  3 = full deepagents orchestration                 (Plan B)

Plan A implements 0 and 1 only. Levels 2/3 are added in Plan B once the
deepagents feasibility spike passes; until then they degrade to level 0.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

_MAX_IMPLEMENTED_LEVEL = 1  # Plan A ships 0 and 1


def ow_harness_level() -> int:
    """Parse TUTOR_OW_HARNESS; out-of-range / unimplemented / junk -> 0 (safe)."""
    raw = os.environ.get("TUTOR_OW_HARNESS", "0").strip()
    try:
        n = int(raw)
    except ValueError:
        return 0
    if n < 0 or n > _MAX_IMPLEMENTED_LEVEL:
        return 0
    return n


_F = TypeVar("_F", bound=Callable)


def maybe_traced(fn: _F, *, name: str) -> _F:
    """Wrap *fn* with LangSmith @traceable when level>=1 AND LANGSMITH_API_KEY is
    set. Otherwise return *fn* unchanged. Tracing NEVER changes behavior; on any
    import/wrap failure, return *fn* unchanged."""
    if ow_harness_level() < 1 or not os.environ.get("LANGSMITH_API_KEY"):
        return fn
    try:
        from langsmith import traceable
        return traceable(name=name)(fn)  # type: ignore[return-value]
    except Exception:  # noqa: BLE001
        logger.exception("LangSmith tracing wrap failed; running untraced")
        return fn
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -v`
Expected: PASS (all tests so far).

- [ ] **Step 5: Wire tracing into the workflow (behavior-identical)**

In `orchestrator_workers.py`, import the harness and wrap the worker + synthesizer calls so L1 traces them. At the top add:

```python
from src.services.chat.agents.ow_harness import maybe_traced
```

Wrap the worker call site: change the `asyncio.gather(*(run_author_worker(...) ...))` to call `maybe_traced(run_author_worker, name="ow.worker")(...)`. Because `maybe_traced` returns the original coroutine function when off, this is a no-op at L0. Verify behavior unchanged:

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py src/services/chat/tests/test_deep_tutor.py -q`
Expected: all pass (L0 default → `run_author_worker` unwrapped → identical).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/ow_harness.py src/services/chat/agents/orchestrator_workers.py src/services/chat/tests/test_ow_harness.py
git commit -m "feat(ow-harness): TUTOR_OW_HARNESS level flag + L1 LangSmith tracing passthrough"
```

---

## Task 5: Baseline eval module (L0 quality + context-fidelity)

**Files:** Create `src/services/chat/eval/ow_harness_compare.py`; Test `src/services/chat/tests/test_ow_harness.py`

- [ ] **Step 1: Write the failing test (append)**

```python
from src.services.chat.eval import ow_harness_compare as OWC


def test_owc_constants_and_helpers():
    assert OWC.JUDGE_MODEL == "gpt-5.4-nano-2026-03-17"
    assert len(OWC.QUESTIONS) == 3
    assert OWC.JUDGE_DIMS == ("faithfulness", "coverage", "synthesis", "coherence")


def test_owc_render_briefs_text():
    from src.services.chat.schemas.output import AuthorBrief
    txt = OWC._briefs_text([AuthorBrief(author="Hansen", summary="s", key_points=["k1"])])
    assert "Hansen" in txt and "k1" in txt


def test_owc_parse_scores_fallback():
    d = OWC._parse_scores("garbage", OWC.JUDGE_DIMS)
    assert d["overall"] == 0.0
    good = '{"faithfulness":5,"coverage":4,"synthesis":4,"coherence":5}'
    g = OWC._parse_scores(good, OWC.JUDGE_DIMS)
    assert g["overall"] == 4.5


def test_owc_render_artifact():
    rows = {("L0", 0): {"level": "L0", "qi": 0, "ok": True, "answer": "A", "briefs": "B",
                        "in_tok": 10, "out_tok": 5, "ms": 100,
                        "quality": {"faithfulness":5,"coverage":4,"synthesis":4,"coherence":5,"overall":4.5},
                        "fidelity": 4.0}}
    md = OWC._render_artifact(rows)
    assert "| level | question |" in md and "L0" in md and "4.5" in md and "fidelity" in md.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -k owc -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# src/services/chat/eval/ow_harness_compare.py
"""Baseline eval for the orchestrator-workers harness ablation (Plan A: L0 only).

Freezes multi-author sources per fan-out question, runs the workflow at L0
(current behavior), captures the worker briefs via on_briefs, and judges the
final answer for quality + context-fidelity (did brief facts survive synthesis).
Plan B appends L1/L2/L3 rows to the same artifact.

Run:
  .venv/bin/python -m src.services.chat.eval.ow_harness_compare --step freeze
  .venv/bin/python -m src.services.chat.eval.ow_harness_compare --step run
  .venv/bin/python -m src.services.chat.eval.ow_harness_compare --step judge
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from src.services.chat._fences import strip_fences

JUDGE_MODEL = "gpt-5.4-nano-2026-03-17"
QUESTIONS = [
    "Compare how different authors define and motivate the bias-variance tradeoff.",
    "Contrast OLS and maximum likelihood estimation across the textbooks.",
    "Compare frequentist and Bayesian treatments of estimation.",
]
BOOKS = None  # all books -> maximises author diversity (orchestrator needs >=2)
TOP_K = 10
MAX_TOK = 700
TIMEOUT_S = 90
JUDGE_DIMS = ("faithfulness", "coverage", "synthesis", "coherence")

_ROOT = Path(__file__).resolve().parents[4]
_WORK = _ROOT / "docs" / "superpowers" / "eval" / "_work_ow"
_FROZEN = _WORK / "frozen_sources.json"
_RESULTS = _WORK / "results.json"
_ARTIFACT = _ROOT / "docs" / "superpowers" / "eval" / "2026-06-04-ow-harness-ablation.md"

_QUALITY_PROMPT = (
    "You score a tutor answer that synthesizes multiple authors, 1-5 each (5=best):\n"
    "faithfulness (claims grounded in the sources), coverage (covers the question's "
    "parts), synthesis (genuinely COMPARES the authors, not just concatenates), "
    "coherence (one throughline).\n"
    'Return ONLY JSON: {"faithfulness":n,"coverage":n,"synthesis":n,"coherence":n}.'
)
_FIDELITY_PROMPT = (
    "You measure CONTEXT FIDELITY: how well the worker briefs' key facts survived "
    "into the final answer. 1-5 (5 = every brief key-point is represented; "
    "1 = most dropped).\n"
    'Return ONLY JSON: {"fidelity":n}.'
)


def _briefs_text(briefs) -> str:
    out = []
    for b in briefs:
        out.append(f"[{b.author}] {b.summary}")
        out.extend(f"  - {k}" for k in b.key_points)
    return "\n".join(out)


def _answer_text(ans) -> str:
    """Flatten a DeepTutorAnswer's aspect fields into one judged string."""
    if ans is None:
        return ""
    parts = []
    for k in ("definition", "intuition", "mechanism", "applications", "comparison",
              "summary", "answer", "body"):
        v = getattr(ans, k, "") or ""
        if v:
            parts.append(str(v))
    return "\n\n".join(parts) or str(ans)


def _parse_scores(raw: str, dims) -> dict:
    try:
        d = json.loads(strip_fences(raw))
        vals = {k: float(d.get(k, 0)) for k in dims}
    except Exception:
        vals = {k: 0.0 for k in dims}
    vals["overall"] = round(sum(vals.values()) / len(dims), 2)
    return vals


def _load_results() -> dict:
    if not _RESULTS.exists():
        return {}
    return {(r["level"], r["qi"]): r for r in json.loads(_RESULTS.read_text(encoding="utf-8"))}


def _save_results(results: dict) -> None:
    _WORK.mkdir(parents=True, exist_ok=True)
    _RESULTS.write_text(json.dumps(list(results.values()), indent=2), encoding="utf-8")


def _render_artifact(results: dict) -> str:
    from src.services.chat.cost import usd_est
    lines = [
        "# Orchestrator-workers harness ablation — baseline (Plan A: L0)", "",
        f"_frozen multi-author sources · judge={JUDGE_MODEL} · model held constant "
        "(nano workers + synth) · quality + context-fidelity_", "",
        "| level | question | overall | faith | coverage | synthesis | coherence | fidelity | out_tok | ms | USD |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (level, qi), r in sorted(results.items()):
        if not r.get("ok"):
            lines.append(f"| {level} | Q{qi} | FAILED |  |  |  |  |  | {r.get('out_tok',0)} | {r.get('ms',0)} | _{r.get('err','')}_ |")
            continue
        q = r.get("quality", {})
        usd = f"${usd_est(JUDGE_MODEL, input_tokens=r['in_tok'], output_tokens=r['out_tok']):.4f}"
        lines.append(
            f"| {level} | Q{qi} | {q.get('overall',0)} | {q.get('faithfulness',0)} | "
            f"{q.get('coverage',0)} | {q.get('synthesis',0)} | {q.get('coherence',0)} | "
            f"{r.get('fidelity',0)} | {r['out_tok']} | {r['ms']} | {usd} |")
    lines += ["", "## Questions", ""]
    for i, q in enumerate(QUESTIONS):
        lines.append(f"- Q{i}: {q}")
    lines += ["", "> Opus verdict + feasibility note (from the spike) appended after review.", ""]
    return "\n".join(lines)


def step_freeze() -> None:
    from src.services.chat.retrieval import hybrid_search
    _WORK.mkdir(parents=True, exist_ok=True)
    frozen = {}
    for qi, q in enumerate(QUESTIONS):
        sources, _ = hybrid_search(q, book_slugs=BOOKS, top_k=TOP_K, rerank=False)
        frozen[str(qi)] = [s.model_dump_json() for s in sources]
        authors = {(s.authors_short or s.book) for s in sources}
        print(f"Q{qi}: {len(sources)} sources, {len(authors)} distinct authors")
    _FROZEN.write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    print(f"wrote {_FROZEN}")


async def step_run() -> None:
    from src.services.chat.agents.orchestrator_workers import run_orchestrator_workers
    from src.services.chat.schemas import Source

    assert _FROZEN.exists(), "run --step freeze first"
    frozen = json.loads(_FROZEN.read_text(encoding="utf-8"))
    results = _load_results()
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
            results[("L0", qi)] = {
                "level": "L0", "qi": qi, "ok": ok,
                "answer": _answer_text(ans), "briefs": _briefs_text(briefs),
                "in_tok": 0, "out_tok": len(_answer_text(ans)) // 4,
                "ms": int((time.monotonic()-t0)*1000),
                "err": "" if ok else "no answer or <2 briefs (fell back to single draft)"}
        except Exception as exc:  # noqa: BLE001
            results[("L0", qi)] = {"level": "L0", "qi": qi, "ok": False, "answer": "",
                                   "briefs": "", "in_tok": 0, "out_tok": 0,
                                   "ms": int((time.monotonic()-t0)*1000),
                                   "err": f"{type(exc).__name__}: {exc}"}
        _save_results(results)
        print(f"[L0 Q{qi}] {'ok' if results[('L0',qi)]['ok'] else 'FAILED: '+results[('L0',qi)]['err']}")


async def step_judge() -> None:
    from src.services.chat.agents.deep_tutor import _async_client
    results = _load_results()
    assert results, "run --step run first"

    async def _judge(system, user) -> str:
        try:
            resp = await asyncio.wait_for(_async_client(JUDGE_MODEL).chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.0, max_completion_tokens=120), timeout=TIMEOUT_S)
            return resp.choices[0].message.content or ""
        except Exception:
            return ""

    for key, r in results.items():
        if not r.get("ok"):
            r["quality"] = _parse_scores("", JUDGE_DIMS); r["fidelity"] = 0.0
            continue
        qtxt = f"SOURCES-BASED ANSWER:\n{r['answer'][:4000]}"
        r["quality"] = _parse_scores(await _judge(_QUALITY_PROMPT, qtxt), JUDGE_DIMS)
        ftxt = f"WORKER BRIEFS:\n{r['briefs'][:2500]}\n\nFINAL ANSWER:\n{r['answer'][:3000]}"
        fid = _parse_scores(await _judge(_FIDELITY_PROMPT, ftxt), ("fidelity",))
        r["fidelity"] = fid.get("fidelity", 0.0)
    _save_results(results)
    _ARTIFACT.write_text(_render_artifact(results), encoding="utf-8")
    print(f"wrote {_ARTIFACT}")


def main() -> None:
    ap = argparse.ArgumentParser(description="orchestrator-workers harness ablation eval")
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

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py -v`
Expected: PASS (all OW tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/eval/ow_harness_compare.py src/services/chat/tests/test_ow_harness.py
git commit -m "eval(ow-harness): L0 baseline + context-fidelity metric harness"
```

---

## Task 6: Lint + full-suite gate

**Files:** none (verification only)

- [ ] **Step 1: Ruff**

Run: `.venv/bin/python -m ruff check src/services/chat/agents/ow_harness.py src/services/chat/agents/orchestrator_workers.py src/services/chat/eval/ow_harness_compare.py src/services/chat/tests/test_ow_harness.py`
Expected: clean (use `ruff` on PATH if `.venv/bin/ruff` missing). Fix inline.

- [ ] **Step 2: Full chat suite**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: all pass.

- [ ] **Step 3: Commit (only if fixes needed)**

```bash
git add -A && git commit -m "chore(ow-harness): lint + test gate green"
```

---

## Task 7: RUN the baseline eval (orchestrator runbook — live API + Qdrant)

> Orchestrator-run. Needs Qdrant up + API keys.

- [ ] **Step 1: Confirm Qdrant**

Run: `curl -s http://localhost:6333/healthz`
Expected: `healthz check passed`.

- [ ] **Step 2: Freeze multi-author sources**

Run: `.venv/bin/python -m src.services.chat.eval.ow_harness_compare --step freeze`
Expected: each Q prints ≥ 2 distinct authors (required for orchestrator-workers to fire). If a question shows < 2 authors, swap it for a broader one in `QUESTIONS` and re-freeze.

- [ ] **Step 3: Run L0**

Run: `.venv/bin/python -m src.services.chat.eval.ow_harness_compare --step run`
Expected: `[L0 Qi] ok` for each; any FAILED is recorded (e.g. fell back to single draft) and non-fatal.

- [ ] **Step 4: Judge + render**

Run: `.venv/bin/python -m src.services.chat.eval.ow_harness_compare --step judge`
Expected: `wrote .../2026-06-04-ow-harness-ablation.md`.

- [ ] **Step 5: Append verdict + spike feasibility**

Read the artifact + the spike findings (`_spike/deepagents-findings.md`). Replace the `> Opus verdict ...` line with: the L0 baseline read (quality + context-fidelity numbers), the **deepagents feasibility verdict** (FEASIBLE → Plan B proceeds with L1/L2/L3; BLOCKED → stop at L1, reasons), and the recommended next step. Edit in place.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/eval/_work_ow docs/superpowers/eval/2026-06-04-ow-harness-ablation.md
git commit -m "eval(ow-harness): L0 baseline run + artifact + feasibility verdict"
```

---

## Task 8: Docs lockstep

**Files:** Create `docs/services/chat-features/55-ow-harness-ablation.md`; Modify `docs/services/chat-features/36-deep-tutor.md`, `docs/system/invariants.md`, `docs/system/changelog.md`

- [ ] **Step 1: Env table row (doc 36)**

Add to the `TUTOR_*` env table in `docs/services/chat-features/36-deep-tutor.md`:

```
| `TUTOR_OW_HARNESS` | `0` | Orchestrator-workers harness level: 0 baseline, 1 LangSmith tracing (behavior identical). Levels 2/3 (deepagents) are Plan B; unimplemented/out-of-range values fall back to 0. |
```

- [ ] **Step 2: Per-feature doc (55)**

Create `docs/services/chat-features/55-ow-harness-ablation.md` summarising: the ablation goal, the 4 levels (L0/L1 shipped, L2/L3 = Plan B pending the spike), the `on_briefs` hook, the context-fidelity metric, the eval module + artifact path, and the `eval-methodology.md` playbook link.

- [ ] **Step 3: Invariant + changelog**

In `docs/system/invariants.md` add:

```
- The orchestrator-workers harness (`TUTOR_OW_HARNESS`) never changes the answer
  at level 0/1 and always falls back to level 0 on any harness failure; LangSmith
  tracing is observability-only and must not alter outputs.
```

In `docs/system/changelog.md` prepend:

```
## 2026-06-04 — Orchestrator-workers harness ablation (Plan A)
Added `TUTOR_OW_HARNESS` (L0 baseline, L1 LangSmith tracing passthrough), an
`on_briefs` capture hook, a context-fidelity eval, and the eval-flow methodology
playbook. deepagents L2/L3 deferred to Plan B pending the feasibility spike.
```

- [ ] **Step 4: Commit**

```bash
git add docs/services/chat-features/55-ow-harness-ablation.md docs/services/chat-features/36-deep-tutor.md docs/system/invariants.md docs/system/changelog.md
git commit -m "docs(ow-harness): doc 55, env table, invariant, changelog (Plan A)"
```

---

## Self-Review

**Spec coverage (Plan A scope):** L0/L1 levels + flag + fallback (Tasks 4); `on_briefs`/context-fidelity (Tasks 3, 5); LangSmith tracing observability-only (Task 4); feasibility spike gate (Task 1); methodology doc (Task 2); frozen-source eval + judge + artifact + verdict (Tasks 5, 7); controlled aspects — caps/timeout/persist/fallback (Tasks 4, 5); docs lockstep (Task 8). **L2/L3 deepagents conversion is explicitly out of Plan A → Plan B** (spec's L2/L3 + modal-card-on-default-flip are deferred; noted in Task 8 doc).

**Placeholder scan:** the spike script's `create_deep_agent` call is the real current deepagents entrypoint but is in a *throwaway* script whose Step 2 explicitly says to confirm the API against the `deep-agents-core` skill first — acceptable for a spike (its job is to discover the API). All shipped code (Tasks 3–5) is concrete. The only literal "verdict appended after review" placeholder is the artifact line Task 7 replaces.

**Type consistency:** `AuthorBrief{author,summary,key_points,source_ranks}` used consistently (Tasks 3, 5); `run_orchestrator_workers(..., on_briefs=None)` signature consistent (Tasks 3, 5); eval row keys (`level/qi/ok/answer/briefs/in_tok/out_tok/ms/quality/fidelity/err`) consistent across `step_run`/`step_judge`/`_render_artifact`; `JUDGE_DIMS` consistent; `ow_harness_level`/`maybe_traced` names consistent (Task 4 → orchestrator_workers wiring).

**Known limitation:** `out_tok` for the workflow answer is estimated (`len//4`) because `run_orchestrator_workers` streams and doesn't return usage; USD is therefore approximate at L0. The judge calls' cost is exact. Acceptable for a baseline; Plan B can thread real usage if a level ships.
```
