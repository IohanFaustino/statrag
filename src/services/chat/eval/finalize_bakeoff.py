# ponytail: one-off bake-off harness, safe to delete
"""Compare finalize-stage models on two stationarity queries.

Runs the deep_tutor pipeline with each model, collects the structured_output,
and prints a human-judgeable block per (model, query) pair.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys

# ── Wire env BEFORE importing deep_tutor (FINALIZE_ON is read at import time) ──
os.environ["TUTOR_FINALIZE"] = "1"

from src.services.chat.schemas._core import ChatRequest
from src.services.chat.agents.deep_tutor import run_deep_tutor, FINALIZE_ON


MODELS = ["deepseek-v4-pro", "gpt-5.4-2026-03-05", "gemini-2.5-pro"]
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


async def main():
    print(f"FINALIZE_ON={FINALIZE_ON}", flush=True)

    results = []
    for model in MODELS:
        for q in QUERIES:
            print(f"\n{'='*60}", flush=True)
            print(f"Running: model={model} query={q[:60]}...", flush=True)
            result = await run_one(model, q)
            if result is None or result["structured"] is None:
                print(f"\n=== MODEL={model} | QUERY={q} ===")
                print("[FAILED — no structured_output received]")
                print("---")
                continue

            data = result["structured"]
            facets = result["facets"]
            text = data.get("text", "")
            formal = data.get("formal_statements", [])

            print(f"\n=== MODEL={model} | QUERY={q} ===")
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