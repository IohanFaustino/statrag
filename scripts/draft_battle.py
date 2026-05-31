"""In-process draft-model battle harness (no HTTP server).

Runs the deep-tutor DRAFT stage directly per candidate model over fixed
queries, measuring wall-clock draft latency, output token count, and capturing
the `definition` aspect for LaTeX/decomposition eyeballing. Equivalent to the
plan's /api/chat battle but server-free (sandbox kills bound servers).

Usage:  .venv/bin/python scripts/draft_battle.py
"""
from __future__ import annotations

import asyncio
import time

import tiktoken

from src.services.chat.agents.deep_tutor import ASPECT_HEADINGS, _stream_draft
from src.services.chat.retrieval import hybrid_search

_ENC = tiktoken.get_encoding("cl100k_base")

QUERIES = [
    "Define variance.",
    "What is the bias-variance tradeoff?",
    "What is overfitting?",
    "Compare L1 and L2 regularization.",
]
VARIANCE_QUERY = "What is the bias-variance tradeoff?"  # run 3x per candidate

CANDIDATES = [
    "gpt-5.4-2026-03-05",       # baseline / incumbent
    "qwen-plus",
    "qwen-max",
    "gemini-2.5-flash",
    "deepseek-v4-pro",          # thinking disabled via DEEPSEEK_DISABLE_THINKING
    "openai/gpt-oss-120b",      # groq (needs GROQ_API_KEY)
    "llama-3.3-70b-versatile",  # groq
]


def _tok(text: str) -> int:
    return len(_ENC.encode(text or ""))


async def _one_draft(query: str, sources, model: str) -> dict:
    t0 = time.monotonic()
    try:
        parsed, acc = await _stream_draft(query, sources, model=model)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "err": f"{type(exc).__name__}: {exc}"}
    dt_ms = int((time.monotonic() - t0) * 1000)
    if parsed is None:
        return {"ok": False, "err": "draft None (unparseable/empty)", "ms": dt_ms}
    aspects = {k: str(getattr(parsed, k, "") or "") for k in ASPECT_HEADINGS}
    out_tok = sum(_tok(v) for v in aspects.values())
    return {
        "ok": True,
        "ms": dt_ms,
        "out_tok": out_tok,
        "definition": aspects.get("definition", ""),
        "n_aspects_filled": sum(1 for v in aspects.values() if v.strip()),
    }


async def main() -> None:
    # Retrieve realistic sources ONCE per query (rerank on, as the tutor does).
    print("Retrieving sources per query...", flush=True)
    sources_by_query: dict[str, list] = {}
    for q in QUERIES:
        srcs, _meta = hybrid_search(q, top_k=8, rerank=True)
        sources_by_query[q] = srcs
        print(f"  {q!r}: {len(srcs)} sources", flush=True)

    results: dict[str, dict[str, list[dict]]] = {c: {} for c in CANDIDATES}
    for cand in CANDIDATES:
        print(f"\n=== {cand} ===", flush=True)
        for q in QUERIES:
            runs = 3 if q == VARIANCE_QUERY else 1
            results[cand][q] = []
            for r in range(runs):
                res = await _one_draft(q, sources_by_query[q], cand)
                results[cand][q].append(res)
                tag = "OK " if res["ok"] else "ERR"
                detail = (
                    f'{res["ms"]}ms tok={res["out_tok"]} aspects={res["n_aspects_filled"]}/6'
                    if res["ok"] else res["err"]
                )
                print(f"  [{tag}] {q[:40]:40} run{r+1}: {detail}", flush=True)

    # ---- Scorecard ----
    print("\n\n================ SCORECARD ================")
    print(f'{"model":26} {"draft_ms (median)":18} {"out_tok min-max (BV x3)":24} {"verdict-data"}')
    for cand in CANDIDATES:
        bv = [r for r in results[cand][VARIANCE_QUERY] if r["ok"]]
        all_ok = [r for q in QUERIES for r in results[cand][q] if r["ok"]]
        if not all_ok:
            errs = {r["err"] for q in QUERIES for r in results[cand][q] if not r["ok"]}
            print(f"{cand:26} ALL FAILED: {errs}")
            continue
        ms_sorted = sorted(r["ms"] for r in all_ok)
        med_ms = ms_sorted[len(ms_sorted) // 2]
        if bv:
            bv_tok = [r["out_tok"] for r in bv]
            swing = max(bv_tok) / max(min(bv_tok), 1)
            bv_str = f'{min(bv_tok)}-{max(bv_tok)} ({swing:.2f}x)'
        else:
            bv_str = "BV all failed"
        print(f"{cand:26} {med_ms:<18} {bv_str:24} runs_ok={len(all_ok)}")

    # ---- Definition aspect dump (LaTeX / decomposition eyeball) ----
    print("\n\n========= DEFINITION ASPECT (bias-variance, run 1) =========")
    for cand in CANDIDATES:
        runs = results[cand].get(VARIANCE_QUERY, [])
        r1 = runs[0] if runs else None
        print(f"\n----- {cand} -----")
        if r1 and r1["ok"]:
            print(r1["definition"][:700])
        else:
            print(f"(failed: {r1['err'] if r1 else 'no run'})")


if __name__ == "__main__":
    asyncio.run(main())
