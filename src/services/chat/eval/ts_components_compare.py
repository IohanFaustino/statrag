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

from pydantic import BaseModel

from src.services.chat._fences import strip_fences

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


def _format_context(sources) -> str:
    """Render retrieved Source objects into a stable, human-readable context block."""
    blocks = []
    for s in sources:
        head = f"[{s.rank}] {s.book_name or s.book} — {s.section} {s.title}".strip()
        prov = f"(authors: {s.authors_short or 'n/a'}; pages {s.page_from}-{s.page_to})"
        body = (s.chunk or s.excerpt or "").strip()
        blocks.append(f"{head} {prov}\n{body}")
    return "\n\n---\n\n".join(blocks)


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
    except Exception as exc:  # noqa: BLE001
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


async def step_api() -> None:
    assert _CONTEXT.exists(), "run --step retrieve first (context.md missing)"
    context = _CONTEXT.read_text(encoding="utf-8")
    for model in API_MODELS:
        res = await _call_answer(model, context)
        _write_answer(model, **res)
        flag = "ok" if res["ok"] else f"FAILED ({res['err']})"
        print(f"[{model}] {flag} out_tok={res['out_tok']} {res['ms']}ms")


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
