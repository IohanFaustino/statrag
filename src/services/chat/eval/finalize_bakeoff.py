# ponytail: one-off bake-off harness, safe to delete
"""Compare finalize-stage models on two stationarity queries.

Runs the deep_tutor pipeline with each model, collects the structured_output,
and prints a human-judgeable block per (model, query) pair.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

# ── Wire env BEFORE importing deep_tutor (FINALIZE_ON is read at import time) ──
os.environ["TUTOR_FINALIZE"] = "1"

from src.services.chat.schemas._core import ChatRequest
from src.services.chat.agents.deep_tutor import run_deep_tutor, FINALIZE_ON


MODELS = ["deepseek-v4-pro", "gpt-5.4-2026-03-05", "gemini-3-pro"]
GEMINI_FALLBACK = "gemini-2.5-pro"
QUERIES = [
    "What is stationarity? What are its versions? What is a unit root?",
    "What is the KPSS and ADF test of stationarity?",
]


def _dollar_balanced(text: str) -> bool:
    count = text.count("$")
    return count % 2 == 0


def _has_raw_backslash_leak(text: str) -> bool:
    # '\\' outside $...$ regions — indicates unrendered LaTeX
    parts = re.split(r"(\$[^$]+\$)", text)
    for i, p in enumerate(parts):
        if i % 2 == 0 and "\\\\" in p:
            return True
    return False


async def run_one(model: str, query: str) -> dict | None:
    req = ChatRequest(
        message=query,
        mode="tutor",
        bookFilter="ALL",
        stageModels={"finalize": model},
    )
    structured = None
    facets = None
    try:
        async for ev in run_deep_tutor(req):
            if ev.get("type") == "structured_output" and ev.get("schema") == "TutorAnswer":
                structured = ev["data"]
            if ev.get("type") == "retrieval_meta":
                meta = ev.get("meta", {})
                facets = meta.get("facets")
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return None
    return {"structured": structured, "facets": facets, "model": model}


async def probe_model(model: str) -> str:
    """Quick probe: send a tiny structured call to check reachability."""
    from src.services.chat.llm.router import get_llm
    from src.services.chat.llm.base import ChatMessage
    try:
        client, resolved = get_llm(model)
        resp = ""
        async for delta in client.stream(
            [ChatMessage(role="user", content="Reply with just: ok")],
            model=resolved,
            temperature=0.0,
            max_tokens=10,
        ):
            if delta:
                resp += delta
        return model
    except Exception:
        return ""


async def main():
    print(f"FINALIZE_ON={FINALIZE_ON}", flush=True)

    # Probe gemini-3-pro reachability
    actual_models = []
    for m in MODELS:
        if m == "gemini-3-pro":
            print(f"Probing {m}...", end=" ", flush=True)
            ok = await probe_model(m)
            if ok:
                print("REACHABLE")
                actual_models.append(m)
            else:
                print(f"UNREACHABLE — falling back to {GEMINI_FALLBACK}")
                actual_models.append(f"{m}->{GEMINI_FALLBACK}(fallback)")
        else:
            actual_models.append(m)

    results = []
    for entry in actual_models:
        # Parse fallback label
        if "->" in entry:
            label, model_id = entry.split("->", 1)
            # Strip "(fallback)" suffix from model_id
            model_id = model_id.replace("(fallback)", "")
        else:
            label = entry
            model_id = entry

        for q in QUERIES:
            print(f"\n{'='*60}", flush=True)
            print(f"Running: model={model_id} query={q[:60]}...", flush=True)
            result = await run_one(model_id, q)
            if result is None or result["structured"] is None:
                print(f"\n=== MODEL={label} | QUERY={q} ===")
                print("[FAILED — no structured_output received]")
                print("---")
                continue

            data = result["structured"]
            facets = result["facets"]
            text = data.get("text", "")
            formal = data.get("formal_statements", [])

            print(f"\n=== MODEL={label} | QUERY={q} ===")
            print(f"[facets]: {facets if facets else 'n/a'}")
            print(f"[formal_statements count]: {len(formal)}")
            print(f"[answer markdown]:")
            print(text)
            print(f"[latex sanity]: dollar_balanced={_dollar_balanced(text)}, "
                  f"has_raw_backslash_leak={_has_raw_backslash_leak(text)}")
            print("---")

    print("\n\nDone.")


if __name__ == "__main__":
    asyncio.run(main())