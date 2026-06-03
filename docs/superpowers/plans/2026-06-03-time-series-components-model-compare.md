# Time-Series-Components Model Comparison — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline eval that retrieves one frozen RAG context for *"What are the components of a time series?"* and compares five contestants' answers (gpt-5.4-nano, gemini-2.5-flash, qwen-plus, Claude Sonnet, Claude Opus) into one judged artifact.

**Architecture:** A single importable module `src/services/chat/eval/ts_components_compare.py` with three CLI steps (`retrieve` → `api` → `judge`), each persisting to disk so the run is resumable and token-burn-proof. Pure helpers (context formatting, answer/judge JSON parsing, artifact rendering) are unit-tested in CI; the network steps run manually via `python -m`. The two Claude contestants are produced by delegated `Agent` subagents that write answer JSON into the same `_work/answers/` dir before the `judge` step.

**Tech Stack:** Python 3.12, existing chat infra (`hybrid_search`, `aclient_for`, `apply_structured_output`, `usd_est`, `strip_fences`), pydantic, tiktoken, pytest.

**Note on spec deviation:** the spec named `scripts/ts_components_compare.py`; this plan places the code at `src/services/chat/eval/ts_components_compare.py` instead so its pure helpers are importable by pytest (matches the existing `facilitate_eval.py` home). Behaviour and CLI are identical; invoke with `.venv/bin/python -m src.services.chat.eval.ts_components_compare --step <s>`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/services/chat/eval/ts_components_compare.py` | the eval module: constants, prompts, schemas, pure helpers, 3 step fns, `main()` |
| `src/services/chat/tests/test_ts_components_compare.py` | CI unit tests for the pure helpers (no network) |
| `docs/superpowers/eval/_work/context.md` | frozen RAG context (produced by `retrieve`) |
| `docs/superpowers/eval/_work/answers/*.json` | per-contestant answers (produced by `api` + agents) |
| `docs/superpowers/eval/2026-06-03-time-series-components-model-compare.md` | the one artifact (produced by `judge`) |

Contestant id → filename: `gpt-5.4-nano-2026-03-17`→`nano.json`, `gemini-2.5-flash`→`gemini.json`, `qwen-plus`→`qwen.json`, Sonnet→`sonnet.json`, Opus→`opus.json`.

Answer JSON shape (every contestant, identical): `{"contestant": str, "model": str, "answer": str, "in_tok": int, "out_tok": int, "ms": int, "ok": bool, "err": str}`.

---

## Task 1: Module skeleton — constants, prompts, schemas

**Files:**
- Create: `src/services/chat/eval/ts_components_compare.py`
- Test: `src/services/chat/tests/test_ts_components_compare.py`

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_ts_components_compare.py
"""Unit tests for the time-series-components comparison eval (pure helpers only)."""
from src.services.chat.eval import ts_components_compare as tc


def test_constants_present():
    assert "components of a time series" in tc.QUESTION.lower()
    assert tc.BOOKS == ["cerqueira", "spark_ts", "pesaran"]
    assert tc.JUDGE_MODEL == "gpt-5.4-nano-2026-03-17"
    assert tc.API_MODELS == [
        "gpt-5.4-nano-2026-03-17", "gemini-2.5-flash", "qwen-plus",
    ]
    # gold = classical four components
    for c in ("trend", "seasonal", "cyclical", "irregular"):
        assert any(c in g.lower() for g in tc.GOLD_COMPONENTS)
    assert tc.MAX_TOK == 700
    assert tc.TIMEOUT_S == 60


def test_prompt_mentions_question_and_json():
    assert "components of a time series" in tc.ANSWER_PROMPT.lower()
    assert '"reasoning"' in tc.ANSWER_PROMPT
    assert '"answer"' in tc.ANSWER_PROMPT


def test_contestant_filename_map():
    assert tc.CONTESTANT_FILE["gpt-5.4-nano-2026-03-17"] == "nano.json"
    assert tc.CONTESTANT_FILE["sonnet"] == "sonnet.json"
    assert tc.CONTESTANT_FILE["opus"] == "opus.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ts_components_compare.py -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError` (module/constants not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# src/services/chat/eval/ts_components_compare.py
"""Offline eval: 5 contestants answer "what are the components of a time series?"
fed the SAME frozen RAG context. One judged artifact.

Contestants:
  - API (this module calls them): gpt-5.4-nano, gemini-2.5-flash, qwen-plus
  - Claude agents (dispatched by the orchestrator, not this module): sonnet, opus

Steps (each persists to disk; resumable):
  retrieve -> _work/context.md
  api      -> _work/answers/{nano,gemini,qwen}.json
  judge    -> the artifact md  (reads ALL _work/answers/*.json)

Run:
  .venv/bin/python -m src.services.chat.eval.ts_components_compare --step retrieve
  .venv/bin/python -m src.services.chat.eval.ts_components_compare --step api
  # (orchestrator dispatches sonnet+opus agents -> _work/answers/*.json)
  .venv/bin/python -m src.services.chat.eval.ts_components_compare --step judge
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from pydantic import BaseModel, Field

QUESTION = "What are the components of a time series?"
RETRIEVE_QUERY = (
    "What are the components of a time series? trend seasonality cyclical irregular"
)
BOOKS = ["cerqueira", "spark_ts", "pesaran"]
TOP_K = 8

JUDGE_MODEL = "gpt-5.4-nano-2026-03-17"
API_MODELS = ["gpt-5.4-nano-2026-03-17", "gemini-2.5-flash", "qwen-plus"]
GOLD_COMPONENTS = [
    "trend (long-run direction)",
    "seasonal (fixed-period cycles)",
    "cyclical (non-fixed-period swings)",
    "irregular / noise (residual)",
]

MAX_TOK = 700
TIMEOUT_S = 60

_ROOT = Path(__file__).resolve().parents[4]
_WORK = _ROOT / "docs" / "superpowers" / "eval" / "_work"
_ANSWERS = _WORK / "answers"
_CONTEXT = _WORK / "context.md"
_ARTIFACT = (
    _ROOT / "docs" / "superpowers" / "eval"
    / "2026-06-03-time-series-components-model-compare.md"
)

CONTESTANT_FILE = {
    "gpt-5.4-nano-2026-03-17": "nano.json",
    "gemini-2.5-flash": "gemini.json",
    "qwen-plus": "qwen.json",
    "sonnet": "sonnet.json",
    "opus": "opus.json",
}
# Order contestants appear in the artifact table.
TABLE_ORDER = [
    "gpt-5.4-nano-2026-03-17", "gemini-2.5-flash", "qwen-plus", "sonnet", "opus",
]

ANSWER_PROMPT = """<role>
You answer one statistics question for a learner, using ONLY the provided context.
</role>

<task>
Answer: "What are the components of a time series?"
</task>

<output_format>
Return ONLY a JSON object:
  "reasoning": 2-4 private sentences planning the answer. DISCARDED, never shown.
  "answer": a clear 250-400 word explanation grounded in the context. Name and
      briefly explain each component. Use $...$ for any math. English only.
</output_format>

<rules>
Ground every claim in the context. If the context omits a classical component,
you may name it but state the context does not cover it. No invented citations.
Fill "reasoning" first, then write a clean "answer".
</rules>
"""


class AnswerOut(BaseModel):
    reasoning: str = ""
    answer: str = ""


JUDGE_PROMPT = (
    "You score a learner-facing answer to 'What are the components of a time "
    "series?', 1-5 each (5=best):\n"
    "clarity (understandable), faithfulness (claims grounded in CONTEXT, no "
    "fabrication), coverage (how many of the gold components are correctly named "
    "and explained), conciseness (tight vs padded).\n"
    "GOLD components: trend, seasonal, cyclical, irregular/noise.\n"
    'Return ONLY JSON: {"clarity":n,"faithfulness":n,"coverage":n,"conciseness":n}.'
)

_JUDGE_DIMS = ("clarity", "faithfulness", "coverage", "conciseness")


class JudgeOut(BaseModel):
    clarity: float = 0.0
    faithfulness: float = 0.0
    coverage: float = 0.0
    conciseness: float = 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description="time-series-components model compare")
    ap.add_argument("--step", choices=["retrieve", "api", "judge"], required=True)
    args = ap.parse_args()
    if args.step == "retrieve":
        step_retrieve()
    elif args.step == "api":
        asyncio.run(step_api())
    else:
        asyncio.run(step_judge())


if __name__ == "__main__":
    main()
```

Add placeholder step fns so the module imports cleanly (filled in later tasks):

```python
def step_retrieve() -> None:  # Task 2
    raise NotImplementedError


async def step_api() -> None:  # Task 3
    raise NotImplementedError


async def step_judge() -> None:  # Task 4
    raise NotImplementedError
```

Place the three placeholder fns ABOVE `main()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ts_components_compare.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/eval/ts_components_compare.py src/services/chat/tests/test_ts_components_compare.py
git commit -m "eval(ts-compare): module skeleton — constants, prompts, schemas"
```

---

## Task 2: Retrieve step — freeze RAG context

**Files:**
- Modify: `src/services/chat/eval/ts_components_compare.py` (add `_format_context`, fill `step_retrieve`)
- Test: `src/services/chat/tests/test_ts_components_compare.py`

- [ ] **Step 1: Write the failing test**

```python
def test_format_context_renders_sources():
    from src.services.chat.schemas import Source
    s = Source(
        rank=1, book="cerqueira", chapter="ch03", section="3.1",
        title="Time Series Decomposition", excerpt="", score=0.9,
        chunkId="x1", chunk="A time series has trend and seasonality.",
        book_name="DL for Time Series", authors_short="Cerqueira",
        page_from=40, page_to=42,
    )
    out = tc._format_context([s])
    assert "[1]" in out
    assert "Time Series Decomposition" in out
    assert "trend and seasonality" in out
    assert "Cerqueira" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ts_components_compare.py::test_format_context_renders_sources -v`
Expected: FAIL — `AttributeError: module has no attribute '_format_context'`.

- [ ] **Step 3: Write minimal implementation**

Add to the module (above `step_retrieve`):

```python
def _format_context(sources) -> str:
    """Render retrieved Source objects into a stable, human-readable context block."""
    blocks = []
    for s in sources:
        head = f"[{s.rank}] {s.book_name or s.book} — {s.section} {s.title}".strip()
        prov = f"(authors: {s.authors_short or 'n/a'}; pages {s.page_from}-{s.page_to})"
        body = (s.chunk or s.excerpt or "").strip()
        blocks.append(f"{head} {prov}\n{body}")
    return "\n\n---\n\n".join(blocks)
```

Fill `step_retrieve`:

```python
def step_retrieve() -> None:
    from src.services.chat.retrieval import hybrid_search
    sources, meta = hybrid_search(
        RETRIEVE_QUERY, book_slugs=BOOKS, top_k=TOP_K, rerank=False,
    )
    ctx = _format_context(sources)
    _WORK.mkdir(parents=True, exist_ok=True)
    header = (
        f"# Frozen RAG context — {QUESTION}\n\n"
        f"_query: {RETRIEVE_QUERY}_\n"
        f"_books: {', '.join(BOOKS)} · top_k={TOP_K} · rerank=False · "
        f"{len(sources)} sources_\n\n"
    )
    _CONTEXT.write_text(header + ctx + "\n", encoding="utf-8")
    print(f"wrote {_CONTEXT} ({len(sources)} sources, {len(ctx)} chars)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ts_components_compare.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/eval/ts_components_compare.py src/services/chat/tests/test_ts_components_compare.py
git commit -m "eval(ts-compare): retrieve step freezes merged RAG context"
```

---

## Task 3: API step — call the trio with hard cap + timeout

**Files:**
- Modify: `src/services/chat/eval/ts_components_compare.py` (add `_parse_answer`, `_call_answer`, fill `step_api`)
- Test: `src/services/chat/tests/test_ts_components_compare.py`

- [ ] **Step 1: Write the failing test**

```python
def test_parse_answer_strips_fences_and_extracts():
    raw = '```json\n{"reasoning":"r","answer":"Trend and seasonality."}\n```'
    assert tc._parse_answer(raw) == "Trend and seasonality."


def test_parse_answer_bad_json_returns_raw_stripped():
    # unparseable -> fall back to the raw text so a judge can still see something
    assert tc._parse_answer("not json at all") == "not json at all"


def test_write_answer_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(tc, "_ANSWERS", tmp_path)
    tc._write_answer("qwen-plus", model="qwen-plus", answer="A.", in_tok=10,
                     out_tok=5, ms=123, ok=True, err="")
    data = tc._load_answers()
    assert data["qwen-plus"]["answer"] == "A."
    assert data["qwen-plus"]["ok"] is True
    assert data["qwen-plus"]["out_tok"] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ts_components_compare.py -k "parse_answer or write_answer" -v`
Expected: FAIL — helpers not defined.

- [ ] **Step 3: Write minimal implementation**

Add to the module:

```python
from src.services.chat._fences import strip_fences  # top-of-file import


def _parse_answer(raw: str) -> str:
    """Pull the 'answer' field out of a model reply; fall back to raw on failure."""
    try:
        data = json.loads(strip_fences(raw))
        ans = str(data.get("answer") or "").strip()
        return ans or strip_fences(raw).strip()
    except Exception:
        return (raw or "").strip()


def _write_answer(contestant: str, **fields) -> None:
    _ANSWERS.mkdir(parents=True, exist_ok=True)
    fname = CONTESTANT_FILE[contestant]
    payload = {"contestant": contestant, **fields}
    (_ANSWERS / fname).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_answers() -> dict:
    """contestant -> payload dict, for every *.json present in _ANSWERS."""
    out = {}
    if not _ANSWERS.exists():
        return out
    for f in sorted(_ANSWERS.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d["contestant"]] = d
    return out


async def _call_answer(model: str, context: str) -> dict:
    """One capped+timed API call. Returns the answer payload (never raises)."""
    from src.services.chat.llm.router import aclient_for
    from src.services.chat.llm.structured import apply_structured_output

    messages = [
        {"role": "system", "content": ANSWER_PROMPT},
        {"role": "user", "content": f"CONTEXT:\n{context}"},
    ]
    messages, response_format = apply_structured_output(messages, model, AnswerOut)
    kwargs = {
        "model": model, "messages": messages, "temperature": 0.0,
        "max_completion_tokens": MAX_TOK,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    oa = aclient_for(model)
    t0 = time.monotonic()
    try:
        resp = await asyncio.wait_for(
            oa.chat.completions.create(**kwargs), timeout=TIMEOUT_S
        )
    except Exception as exc:  # noqa: BLE001  (timeout, API error, etc.)
        ms = int((time.monotonic() - t0) * 1000)
        return {"model": model, "answer": "", "in_tok": 0, "out_tok": 0,
                "ms": ms, "ok": False, "err": f"{type(exc).__name__}: {exc}"}
    ms = int((time.monotonic() - t0) * 1000)
    raw = resp.choices[0].message.content or ""
    u = getattr(resp, "usage", None)
    return {
        "model": model, "answer": _parse_answer(raw),
        "in_tok": int(getattr(u, "prompt_tokens", 0) or 0),
        "out_tok": int(getattr(u, "completion_tokens", 0) or 0),
        "ms": ms, "ok": True, "err": "",
    }
```

Fill `step_api`:

```python
async def step_api() -> None:
    assert _CONTEXT.exists(), "run --step retrieve first (context.md missing)"
    context = _CONTEXT.read_text(encoding="utf-8")
    for model in API_MODELS:
        res = await _call_answer(model, context)
        _write_answer(model, **res)  # persist immediately (token-burn safety)
        flag = "ok" if res["ok"] else f"FAILED ({res['err']})"
        print(f"[{model}] {flag} out_tok={res['out_tok']} {res['ms']}ms")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ts_components_compare.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/eval/ts_components_compare.py src/services/chat/tests/test_ts_components_compare.py
git commit -m "eval(ts-compare): api step — capped+timed trio calls, persisted per-call"
```

---

## Task 4: Judge step + artifact rendering

**Files:**
- Modify: `src/services/chat/eval/ts_components_compare.py` (add `_parse_judge`, `_render_artifact`, fill `step_judge`)
- Test: `src/services/chat/tests/test_ts_components_compare.py`

- [ ] **Step 1: Write the failing test**

```python
def test_parse_judge_ok_and_fallback():
    good = '{"clarity":5,"faithfulness":4,"coverage":3,"conciseness":4}'
    d = tc._parse_judge(good)
    assert d == {"clarity": 5.0, "faithfulness": 4.0, "coverage": 3.0,
                 "conciseness": 4.0, "overall": 4.0}
    bad = tc._parse_judge("garbage")
    assert bad["overall"] == 0.0
    assert bad["clarity"] == 0.0


def test_render_artifact_has_table_and_answers():
    answers = {
        "gpt-5.4-nano-2026-03-17": {
            "contestant": "gpt-5.4-nano-2026-03-17", "model": "gpt-5.4-nano-2026-03-17",
            "answer": "Trend, seasonal, cyclical, irregular.", "in_tok": 500,
            "out_tok": 200, "ms": 1200, "ok": True, "err": "",
        },
        "sonnet": {
            "contestant": "sonnet", "model": "claude-sonnet", "answer": "Four parts.",
            "in_tok": 0, "out_tok": 0, "ms": 0, "ok": True, "err": "",
        },
    }
    scores = {
        "gpt-5.4-nano-2026-03-17": {"clarity": 5.0, "faithfulness": 5.0,
                                    "coverage": 5.0, "conciseness": 4.0, "overall": 4.75},
        "sonnet": {"clarity": 4.0, "faithfulness": 4.0, "coverage": 3.0,
                   "conciseness": 5.0, "overall": 4.0},
    }
    md = tc._render_artifact(answers, scores)
    assert "| contestant |" in md
    assert "gpt-5.4-nano-2026-03-17" in md
    assert "4.75" in md          # overall rendered
    assert "$" in md             # USD column present
    assert "## Full answers" in md
    assert "Trend, seasonal, cyclical, irregular." in md
    assert "_(agent — no API cost)_" in md or "n/a" in md  # agent cost cell
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ts_components_compare.py -k "judge or render" -v`
Expected: FAIL — helpers not defined.

- [ ] **Step 3: Write minimal implementation**

Add to the module:

```python
def _parse_judge(raw: str) -> dict:
    """Parse judge JSON to {dims..., overall}; unparseable -> all zeros."""
    try:
        d = json.loads(strip_fences(raw))
        vals = {k: float(d.get(k, 0)) for k in _JUDGE_DIMS}
    except Exception:
        vals = {k: 0.0 for k in _JUDGE_DIMS}
    vals["overall"] = round(sum(vals.values()) / len(_JUDGE_DIMS), 2)
    return vals


def _render_artifact(answers: dict, scores: dict) -> str:
    from src.services.chat.cost import usd_est

    lines = [
        f"# Model comparison — {QUESTION}",
        "",
        f"_5 contestants · identical frozen RAG context "
        f"({', '.join(BOOKS)}) · judge={JUDGE_MODEL} (fixed) · "
        "prompt-reasoning scratchpad (discarded) · 1 run each_",
        "",
        "**Gold components:** " + "; ".join(GOLD_COMPONENTS),
        "",
        "| contestant | overall | clarity | faith | coverage | concise | "
        "out_tok | ms | USD |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in TABLE_ORDER:
        if c not in answers:
            lines.append(f"| {c} | _(missing answer)_ |  |  |  |  |  |  |  |")
            continue
        a = answers[c]
        sc = scores.get(c, {k: 0.0 for k in (*_JUDGE_DIMS, "overall")})
        if not a.get("ok", False):
            lines.append(
                f"| {c} | FAILED |  |  |  |  | {a.get('out_tok', 0)} | "
                f"{a.get('ms', 0)} | _{a.get('err', '')}_ |"
            )
            continue
        is_agent = c in ("sonnet", "opus")
        usd = "_(agent — no API cost)_" if is_agent else (
            f"${usd_est(a['model'], input_tokens=a['in_tok'], output_tokens=a['out_tok']):.4f}"
        )
        lines.append(
            f"| {c} | {sc['overall']} | {sc['clarity']} | {sc['faithfulness']} | "
            f"{sc['coverage']} | {sc['conciseness']} | {a['out_tok']} | {a['ms']} | {usd} |"
        )

    winner = max(
        (c for c in TABLE_ORDER if c in scores),
        key=lambda c: scores[c]["overall"], default="(none)",
    )
    lines += ["", f"**Top LLM-judge score:** {winner}", "",
              "> Opus qualitative verdict appended below after manual review.", "",
              "## Full answers", ""]
    for c in TABLE_ORDER:
        if c not in answers:
            continue
        a = answers[c]
        lines += [f"### {c}", "", a.get("answer") or "_(no answer)_", ""]
    return "\n".join(lines)
```

Fill `step_judge`:

```python
async def step_judge() -> None:
    from src.services.chat.llm.router import aclient_for
    from src.services.chat.llm.structured import apply_structured_output

    assert _CONTEXT.exists(), "context.md missing — run --step retrieve"
    context = _CONTEXT.read_text(encoding="utf-8")
    answers = _load_answers()
    assert answers, "no answers found — run --step api and dispatch the agents first"

    async def judge_one(answer: str) -> dict:
        messages = [
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user",
             "content": f"CONTEXT:\n{context[:4000]}\n\nANSWER:\n{answer}"},
        ]
        messages, rf = apply_structured_output(messages, JUDGE_MODEL, JudgeOut)
        kwargs = {"model": JUDGE_MODEL, "messages": messages, "temperature": 0.0,
                  "max_completion_tokens": 120}
        if rf is not None:
            kwargs["response_format"] = rf
        try:
            resp = await asyncio.wait_for(
                aclient_for(JUDGE_MODEL).chat.completions.create(**kwargs),
                timeout=TIMEOUT_S,
            )
            return _parse_judge(resp.choices[0].message.content or "")
        except Exception:
            return _parse_judge("")

    scores = {}
    for c, a in answers.items():
        scores[c] = await judge_one(a.get("answer", "")) if a.get("ok") else _parse_judge("")
    md = _render_artifact(answers, scores)
    _ARTIFACT.write_text(md, encoding="utf-8")
    print(f"wrote {_ARTIFACT}")
    print("\n".join(md.splitlines()[:14]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ts_components_compare.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/eval/ts_components_compare.py src/services/chat/tests/test_ts_components_compare.py
git commit -m "eval(ts-compare): judge step + single-artifact rendering"
```

---

## Task 5: Lint + full unit-test gate

**Files:** none (verification only)

- [ ] **Step 1: Run ruff + mypy on the new module**

Run: `.venv/bin/python -m ruff check src/services/chat/eval/ts_components_compare.py src/services/chat/tests/test_ts_components_compare.py`
Expected: no errors. Fix any inline.

- [ ] **Step 2: Run the full new test file**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ts_components_compare.py -v`
Expected: PASS (9 tests).

- [ ] **Step 3: Confirm no CI regression**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: all pass (existing suite + the 9 new tests).

- [ ] **Step 4: Commit (only if fixes were needed)**

```bash
git add -A && git commit -m "eval(ts-compare): lint + test gate green"
```

---

## Task 6: RUN the eval (orchestrator runbook — manual, needs live API + Qdrant)

> This task is executed by the orchestrator (the main session), not a subagent. It produces the actual data + artifact. Needs Qdrant up and API keys in `.env`.

- [ ] **Step 1: Confirm Qdrant up**

Run: `curl -s http://localhost:6333/healthz`
Expected: `healthz check passed`. If not: `docker compose -f ops/docker/docker-compose.yml up -d`.

- [ ] **Step 2: Retrieve + freeze context**

Run: `.venv/bin/python -m src.services.chat.eval.ts_components_compare --step retrieve`
Expected: `wrote .../_work/context.md (N sources, M chars)` with N ≥ 3.
Then read `docs/superpowers/eval/_work/context.md` and confirm it contains real time-series-decomposition text (trend/seasonality). If empty/irrelevant, widen `BOOKS` or `RETRIEVE_QUERY` and rerun.

- [ ] **Step 3: Run the API trio**

Run: `.venv/bin/python -m src.services.chat.eval.ts_components_compare --step api`
Expected: three lines `[model] ok out_tok=… …ms`. Any `FAILED` line is recorded in its JSON and is non-fatal — note it. Confirm `_work/answers/{nano,gemini,qwen}.json` exist.

- [ ] **Step 4: Dispatch the two Claude agents (Sonnet + Opus)**

Read `docs/superpowers/eval/_work/context.md`. Dispatch TWO `Agent` calls (may run in parallel), one `model: sonnet`, one `model: opus`. Give each agent this exact prompt (substituting `<CONTEXT>` with the file's content and `<OUTFILE>` with the matching path):

```
You are a contestant in a model comparison. Answer ONE question using ONLY the
context below — the same context every other contestant received.

QUESTION: What are the components of a time series?

Write a clear 250-400 word answer. Name and briefly explain each component.
Use $...$ for any math. Ground every claim in the context; if the context omits
a classical component you may name it but say the context does not cover it.

Then write your answer as JSON to the file <OUTFILE> using the Write tool, with
EXACTLY this shape (no other keys):
{"contestant": "<sonnet|opus>", "model": "<your model name>", "answer": "<your 250-400 word answer>",
 "in_tok": 0, "out_tok": 0, "ms": 0, "ok": true, "err": ""}

CONTEXT:
<CONTEXT>
```

- sonnet → `docs/superpowers/eval/_work/answers/sonnet.json`
- opus → `docs/superpowers/eval/_work/answers/opus.json`

Confirm both files exist and parse as JSON with the required keys.

- [ ] **Step 5: Judge + render the artifact**

Run: `.venv/bin/python -m src.services.chat.eval.ts_components_compare --step judge`
Expected: `wrote .../2026-06-03-time-series-components-model-compare.md` and a printed table head with 5 contestant rows (or FAILED/missing where applicable).

- [ ] **Step 6: Append the Opus qualitative verdict**

Read the artifact + all five answers. Replace the line
`> Opus qualitative verdict appended below after manual review.` with a real
2-4 paragraph verdict: which answer best matches the gold four components, who
hallucinated beyond context, cost/quality tradeoff (cheap nano vs the rest),
and a final recommendation. Edit the artifact file in place.

- [ ] **Step 7: Commit the artifact + intermediates**

```bash
git add docs/superpowers/eval/_work docs/superpowers/eval/2026-06-03-time-series-components-model-compare.md
git commit -m "eval(ts-compare): run results + artifact (5 contestants, time-series components)"
```

---

## Self-Review

**Spec coverage:**
- 5 contestants, frozen RAG context, prompt-reasoning, nano judge + gold, USD/latency/tokens, one artifact, Opus verdict — all covered (Tasks 1–4 build, Task 6 runs).
- Robustness: retrieve-once (Task 2), hard cap + `asyncio.wait_for` timeout (Task 3), per-call try/except + immediate persist (Task 3), incremental artifact + missing/FAILED cells (Task 4) — covered.
- Reuse `hybrid_search`/`aclient_for`/`apply_structured_output`/`usd_est`/`strip_fences` — covered.

**Placeholder scan:** no TBD/TODO; every code step shows full code; test code is concrete.

**Type consistency:** answer payload keys (`contestant/model/answer/in_tok/out_tok/ms/ok/err`) consistent across `_write_answer`, `_call_answer`, `_render_artifact`, agent runbook. `_JUDGE_DIMS` + `overall` consistent across `_parse_judge`/`_render_artifact`. `CONTESTANT_FILE`/`TABLE_ORDER` use the same ids throughout.

**Deviation logged:** module path moved from `scripts/` to `src/services/chat/eval/` for testability (noted in header).
