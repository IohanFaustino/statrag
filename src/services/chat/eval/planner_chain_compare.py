"""Offline eval: compare the chained planner across nano/gemini/qwen-plus, plus the
single-call (nano) baseline, on 3 fixed questions. Judge the produced plan. No Qdrant.

Run:
  .venv/bin/python -m src.services.chat.eval.planner_chain_compare --step run
  .venv/bin/python -m src.services.chat.eval.planner_chain_compare --step judge
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from src.services.chat._fences import strip_fences

MODELS = ["gpt-5.4-nano-2026-03-17", "gemini-2.5-flash", "qwen-plus"]
JUDGE_MODEL = "gpt-5.4-nano-2026-03-17"
QUESTIONS = [
    "State the bias of an unbiased estimator.",
    "What are the components of a time series?",
    "Compare L1 and L2 regularization.",
]
MAX_TOK = 300
TIMEOUT_S = 60
JUDGE_DIMS = ("decomposition", "coverage", "targeting", "redundancy")

_ROOT = Path(__file__).resolve().parents[4]
_WORK = _ROOT / "docs" / "superpowers" / "eval" / "_work_planner"
_RESULTS = _WORK / "results.json"
_ARTIFACT = _ROOT / "docs" / "superpowers" / "eval" / "2026-06-04-planner-chain-model-compare.md"

JUDGE_PROMPT = (
    "You score a query planner's output for a stats/ML tutor, 1-5 each (5=best):\n"
    "decomposition (are the sub-questions/facets atomic and complete for the "
    "question?), coverage (do facets include an application-case and a "
    "related-framings facet?), targeting (are queries self-contained and textbook-"
    "phrased, ~one per facet, NOT echoes of the question?), redundancy (5=no "
    "duplication, 1=heavy dup).\n"
    'Return ONLY JSON: {"decomposition":n,"coverage":n,"targeting":n,"redundancy":n}.'
)


def _render_plan(plan: dict) -> str:
    parts = []
    if plan.get("sub_questions"):
        parts.append("sub_questions:\n" + "\n".join(f"- {s}" for s in plan["sub_questions"]))
    parts.append(f"concepts: {plan.get('concepts')}")
    parts.append(f"perspectives: {plan.get('perspectives')}")
    parts.append("facets:\n" + "\n".join(f"- {f}" for f in (plan.get("facets") or [])))
    parts.append("queries:\n" + "\n".join(f"- {q}" for q in (plan.get("queries") or [])))
    return "\n".join(parts)


def _parse_judge(raw: str) -> dict:
    try:
        d = json.loads(strip_fences(raw))
        vals = {k: float(d.get(k, 0)) for k in JUDGE_DIMS}
    except Exception:
        vals = {k: 0.0 for k in JUDGE_DIMS}
    vals["overall"] = round(sum(vals.values()) / len(JUDGE_DIMS), 2)
    return vals


def _load_results() -> dict:
    if not _RESULTS.exists():
        return {}
    raw = json.loads(_RESULTS.read_text(encoding="utf-8"))
    return {(r["model"], r["qi"]): r for r in raw}


def _save_results(results: dict) -> None:
    _WORK.mkdir(parents=True, exist_ok=True)
    rows = []
    for (model, qi), r in results.items():
        rows.append({**r, "model": model, "qi": qi})
    _RESULTS.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _render_artifact(results: dict) -> str:
    from src.services.chat.cost import usd_est

    lines = [
        "# Planner-chain model comparison — decompose→expand→consolidate", "",
        f"_contestants run the 3-step chain (baseline = single-call nano) · "
        f"judge={JUDGE_MODEL} · {len(QUESTIONS)} questions · plan-quality only_", "",
        "| contestant | question | overall | decomp | coverage | targeting | redundancy | out_tok | ms | USD |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (model, qi), r in sorted(results.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        sc = r.get("scores", {k: 0.0 for k in (*JUDGE_DIMS, "overall")})
        label = r.get("label", model)
        if not r.get("ok", False):
            lines.append(f"| {label} | Q{qi} | FAILED |  |  |  |  | {r.get('out_tok',0)} | {r.get('ms',0)} | _{r.get('err','')}_ |")
            continue
        usd = f"${usd_est(model, input_tokens=r['in_tok'], output_tokens=r['out_tok']):.4f}"
        lines.append(
            f"| {label} | Q{qi} | {sc['overall']} | {sc['decomposition']} | {sc['coverage']} | "
            f"{sc['targeting']} | {sc['redundancy']} | {r['out_tok']} | {r['ms']} | {usd} |")
    lines += ["", "## Questions", ""]
    for i, q in enumerate(QUESTIONS):
        lines.append(f"- Q{i}: {q}")
    lines += ["", "## Plan dumps", ""]
    for (model, qi), r in sorted(results.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        lines += [f"### {r.get('label', model)} — Q{qi}", "", "```", r.get("plan_text", "(none)"), "```", ""]
    lines += ["", "> Opus verdict appended after manual review.", ""]
    return "\n".join(lines)


async def _call_usage(model: str, messages: list[dict]) -> tuple[str, int, int]:
    from src.services.chat.agents.deep_tutor import _async_client
    resp = await asyncio.wait_for(
        _async_client(model).chat.completions.create(
            model=model, messages=messages, temperature=0.0, max_completion_tokens=MAX_TOK),
        timeout=TIMEOUT_S)
    u = getattr(resp, "usage", None)
    return (resp.choices[0].message.content or "{}",
            int(getattr(u, "prompt_tokens", 0) or 0),
            int(getattr(u, "completion_tokens", 0) or 0))


def _short(model: str) -> str:
    if model.startswith("gpt-5.4-nano"):
        return "nano"
    if model.startswith("gemini"):
        return "gemini"
    if model.startswith("qwen"):
        return "qwen"
    return model


async def step_run() -> None:
    from src.services.chat.agents import deep_tutor as DT

    results = _load_results()
    for model in MODELS:
        for qi, q in enumerate(QUESTIONS):
            t0 = time.monotonic()
            itok = otok = 0
            try:
                raw, i1, o1 = await _call_usage(
                    model, [{"role": "system", "content": DT.PLANNER_DECOMPOSE_PROMPT},
                            {"role": "user", "content": q}])
                itok += i1
                otok += o1
                subqs = DT._parse_decompose(raw)

                numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(subqs, 1))
                euser = f"original question: {q}\n\nsub-questions:\n{numbered}"
                raw, i2, o2 = await _call_usage(
                    model, [{"role": "system", "content": DT.PLANNER_EXPAND_PROMPT},
                            {"role": "user", "content": euser}])
                itok += i2
                otok += o2
                items = DT._parse_expand(raw)

                clines = [f"- sub_question: {it['sub_question']}\n  concept: {it['concept']}\n"
                          f"  query: {it['query']}\n  facet: {it['facet']}" for it in items]
                cuser = "expanded items:\n" + "\n".join(clines)
                raw, i3, o3 = await _call_usage(
                    model, [{"role": "system",
                             "content": DT.PLANNER_CONSOLIDATE_PROMPT.format(max_authors=4)},
                            {"role": "user", "content": cuser}])
                itok += i3
                otok += o3
                plan = DT._parse_consolidate(raw, 4)

                pd = {"sub_questions": subqs, "concepts": plan.concepts,
                      "perspectives": plan.suggested_authors, "facets": plan.facets, "queries": plan.queries}
                results[(model, qi)] = {"model": model, "qi": qi, "label": f"{_short(model)}-chain",
                                        "plan_text": _render_plan(pd), "in_tok": itok, "out_tok": otok,
                                        "ms": int((time.monotonic()-t0)*1000), "ok": True, "err": ""}
            except Exception as exc:  # noqa: BLE001
                results[(model, qi)] = {"model": model, "qi": qi, "label": f"{_short(model)}-chain",
                                        "plan_text": "", "in_tok": itok, "out_tok": otok,
                                        "ms": int((time.monotonic()-t0)*1000), "ok": False,
                                        "err": f"{type(exc).__name__}: {exc}"}
            _save_results(results)
            print(f"[{model} Q{qi}] {'ok' if results[(model,qi)]['ok'] else 'FAILED'} "
                  f"out_tok={results[(model,qi)]['out_tok']} {results[(model,qi)]['ms']}ms")

    bmodel = JUDGE_MODEL
    for qi, q in enumerate(QUESTIONS):
        t0 = time.monotonic()
        try:
            raw, it, ot = await _call_usage(
                bmodel, [{"role": "system",
                          "content": DT.EXTRACT_CONCEPTS_BUDGET_PROMPT.format(max_authors=4)},
                         {"role": "user", "content": q}])
            parsed = json.loads(strip_fences(raw))
            concepts = [str(x).strip() for x in (parsed.get("concepts") or []) if str(x).strip()][:3]
            n = max(1, min(4, int(parsed.get("perspectives", 2))))
            facets = [str(x).strip() for x in (parsed.get("facets") or []) if str(x).strip()][:6]
            queries = [str(x).strip() for x in (parsed.get("queries") or []) if str(x).strip()][:5]
            pd = {"concepts": concepts, "perspectives": n, "facets": facets, "queries": queries}
            results[("baseline", qi)] = {"model": bmodel, "qi": qi, "label": "single-call(nano) baseline",
                                         "plan_text": _render_plan(pd), "in_tok": it, "out_tok": ot,
                                         "ms": int((time.monotonic()-t0)*1000), "ok": True, "err": ""}
        except Exception as exc:  # noqa: BLE001
            results[("baseline", qi)] = {"model": bmodel, "qi": qi, "label": "single-call(nano) baseline",
                                         "plan_text": "", "in_tok": 0, "out_tok": 0,
                                         "ms": int((time.monotonic()-t0)*1000), "ok": False, "err": f"{type(exc).__name__}: {exc}"}
        _save_results(results)
        print(f"[baseline Q{qi}] {'ok' if results[('baseline',qi)]['ok'] else 'FAILED'}")


async def step_judge() -> None:
    from src.services.chat.agents.deep_tutor import _async_client

    results = _load_results()
    assert results, "no results — run --step run first"

    async def judge_one(qi: int, plan_text: str) -> dict:
        user = f"QUESTION: {QUESTIONS[qi]}\n\nPLANNER OUTPUT:\n{plan_text}"
        try:
            resp = await asyncio.wait_for(_async_client(JUDGE_MODEL).chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": user}],
                temperature=0.0, max_completion_tokens=120), timeout=TIMEOUT_S)
            return _parse_judge(resp.choices[0].message.content or "")
        except Exception:
            return _parse_judge("")

    for key, r in results.items():
        r["scores"] = await judge_one(r["qi"], r.get("plan_text", "")) if r.get("ok") else _parse_judge("")
    _save_results(results)
    _ARTIFACT.write_text(_render_artifact(results), encoding="utf-8")
    print(f"wrote {_ARTIFACT}")


def main() -> None:
    ap = argparse.ArgumentParser(description="planner-chain model compare")
    ap.add_argument("--step", choices=["run", "judge"], required=True)
    args = ap.parse_args()
    asyncio.run(step_run() if args.step == "run" else step_judge())


if __name__ == "__main__":
    main()
