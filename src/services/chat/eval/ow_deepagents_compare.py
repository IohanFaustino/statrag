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
