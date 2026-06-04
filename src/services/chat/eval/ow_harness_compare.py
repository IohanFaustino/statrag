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
BOOKS = ["hansen", "wooldridge", "stock_watson", "gujarati",
         "baltagi", "pesaran", "islp", "murphy"]
TOP_K = 12
LEVELS = [0, 2, 3]  # 0 baseline, 2 structured handoff, 3 deepagents synth
_LEVEL_LABEL = {0: "L0", 2: "L2", 3: "L3"}
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
    "into the final answer. IGNORE any brief that states the source does not discuss "
    "the topic (no-info briefs) — score only content-bearing briefs. 1-5 (5 = every "
    "content-bearing key-point is represented; 1 = most dropped). If there are no "
    "content-bearing briefs, return 0.\n"
    'Return ONLY JSON: {"fidelity":n}.'
)


def _briefs_text(briefs) -> str:
    out = []
    for b in briefs:
        out.append(f"[{b.author}] {b.summary}")
        out.extend(f"  - {k}" for k in b.key_points)
    return "\n".join(out)


def _answer_text(ans) -> str:
    """Flatten a DeepTutorAnswer's real aspect fields into one judged string."""
    if ans is None:
        return ""
    parts = []
    # Actual DeepTutorAnswer text fields (schemas/output.py).
    for k in ("tldr", "definition", "formal_statement", "example_intuition",
              "applications", "further_reading"):
        v = getattr(ans, k, "") or ""
        if v:
            parts.append(str(v))
    # The author-comparison sub-object — central to the synthesis dimension.
    cmp = getattr(ans, "comparison", None)
    if cmp is not None:
        for k in ("author_a", "position_a", "author_b", "position_b"):
            v = getattr(cmp, k, "") or ""
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
            r["quality"] = _parse_scores("", JUDGE_DIMS)
            r["fidelity"] = 0.0
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
