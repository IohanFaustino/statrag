"""CLI orchestrator for the evaluation harness.

Loads a Q/A set, posts each question to the chat backend via HTTP (SSE),
computes 4 metrics per record, writes a timestamped JSON report, and
applies a regression gate against a baseline file.

Wall rule: invokes the chat service over HTTP — NOT via direct import.
No import of src.services.chat.

CLI usage:
    python -m src.services.eval.runner \\
        --set base50 --mode tutor --backend http://localhost:8765
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.core.config import ROOT
from src.services.eval.dataset import QARecord, load
from src.services.eval.metrics import (
    answer_relevance,
    context_precision,
    context_recall,
    faithfulness,
)

logger = logging.getLogger(__name__)

DATA_EVAL = ROOT / "data" / "eval"
REPORTS_DIR = DATA_EVAL / "reports"
BASELINES_PATH = DATA_EVAL / "baselines.json"

_SSE_DATA_PREFIX = "data:"
_SSE_EVENT_PREFIX = "event:"


def _parse_sse(raw: str) -> list[dict]:
    """Parse raw SSE bytes into a list of event dicts with ``event`` and ``data`` keys.

    Args:
        raw: Full SSE response body as a string.

    Returns:
        List of parsed event dicts.
    """
    events: list[dict] = []
    current: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.rstrip()
        if line.startswith(_SSE_EVENT_PREFIX):
            current["event"] = line[len(_SSE_EVENT_PREFIX):].strip()
        elif line.startswith(_SSE_DATA_PREFIX):
            payload = line[len(_SSE_DATA_PREFIX):].strip()
            try:
                current["data"] = json.loads(payload)
            except json.JSONDecodeError:
                current["data"] = payload
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


def _extract_answer_and_sources(events: list[dict]) -> tuple[str, list[dict]]:
    """Extract accumulated answer text and sources_full from SSE events.

    Args:
        events: Parsed SSE event list from the chat backend.

    Returns:
        Tuple of (answer_text, sources_full_list).
    """
    tokens: list[str] = []
    sources: list[dict] = []
    for ev in events:
        data = ev.get("data", {})
        if not isinstance(data, dict):
            continue
        event_type = ev.get("event", "")
        if event_type == "token":
            tokens.append(data.get("text", ""))
        elif event_type == "meta":
            sf = data.get("sources_full")
            if isinstance(sf, list):
                sources = sf
        elif event_type == "done":
            sf = data.get("sources_full")
            if isinstance(sf, list):
                sources = sf
    return "".join(tokens), sources


async def _call_chat(
    client: httpx.AsyncClient,
    backend: str,
    mode: str,
    question: str,
) -> tuple[str, list[dict]]:
    """POST to the chat SSE endpoint and return (answer, sources_full).

    Args:
        client: Shared async HTTP client.
        backend: Base URL of the chat backend (e.g. http://localhost:8765).
        mode: Chat mode identifier (e.g. "tutor").
        question: The user question text.

    Returns:
        Tuple of (answer_text, sources_full_list).

    Raises:
        httpx.HTTPError: On connection or HTTP errors.
    """
    url = f"{backend.rstrip('/')}/api/chat"
    payload = {"mode": mode, "query": question}
    resp = await client.post(url, json=payload, timeout=60.0)
    resp.raise_for_status()
    events = _parse_sse(resp.text)
    return _extract_answer_and_sources(events)


async def _run_record(
    client: httpx.AsyncClient,
    backend: str,
    mode: str,
    record: QARecord,
) -> dict:
    """Run one Q/A record through the chat backend and compute all 4 metrics.

    Args:
        client: Shared async HTTP client.
        backend: Base URL of the chat backend.
        mode: Chat mode identifier.
        record: The Q/A record to evaluate.

    Returns:
        Per-record result dict suitable for JSON serialisation.
    """
    result: dict = {
        "id": record.id,
        "q": record.q,
        "gold_chunk_id": record.gold_chunk_id,
        "error": None,
        "context_precision": 0.0,
        "context_recall": 0.0,
        "faithfulness": 0.0,
        "answer_relevance": 0.0,
    }

    try:
        answer, sources = await _call_chat(client, backend, mode, record.q)
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        logger.warning("HTTP error for record %s: %s", record.id, exc)
        return result

    context_texts = [
        s.get("text") or s.get("excerpt") or "" for s in sources if isinstance(s, dict)
    ]

    result["context_precision"] = context_precision(sources, record.gold_chunk_id)
    result["context_recall"] = context_recall(sources, record.gold_chunk_id)

    try:
        result["faithfulness"] = await faithfulness(answer, context_texts)
    except Exception as exc:  # noqa: BLE001
        logger.warning("faithfulness metric failed for %s: %s", record.id, exc)

    try:
        result["answer_relevance"] = await answer_relevance(answer, record.q)
    except Exception as exc:  # noqa: BLE001
        logger.warning("answer_relevance metric failed for %s: %s", record.id, exc)

    return result


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _check_regression(
    aggregate: dict[str, float],
    mode: str,
) -> bool:
    """Compare aggregate metrics to the stored baseline.

    Updates the baseline file if none exists for the current mode.

    Args:
        aggregate: Current aggregated metric dict.
        mode: Chat mode being evaluated.

    Returns:
        True if any metric has dropped more than 5% vs baseline, False otherwise.
    """
    if not BASELINES_PATH.exists():
        baselines: dict = {}
    else:
        with open(BASELINES_PATH) as f:
            baselines = json.load(f)

    if mode not in baselines:
        # First run — persist as new baseline
        baselines[mode] = aggregate
        BASELINES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BASELINES_PATH, "w") as f:
            json.dump(baselines, f, indent=2)
        logger.info("No baseline for mode '%s' — saved current metrics as baseline.", mode)
        return False

    regression = False
    baseline = baselines[mode]
    for metric, current_val in aggregate.items():
        base_val = baseline.get(metric)
        if base_val is None:
            continue
        if current_val < base_val - 0.05:
            logger.error(
                "REGRESSION: %s %s dropped from %.4f to %.4f (>5%%)",
                mode,
                metric,
                base_val,
                current_val,
            )
            regression = True
    return regression


async def _run(
    set_name: str,
    mode: str,
    backend: str,
) -> int:
    """Core async runner: load set, evaluate all records, write report.

    Args:
        set_name: Base name of the eval set (e.g. "base50").
        mode: Chat mode to test.
        backend: Base URL of the chat backend.

    Returns:
        Exit code — 0 for success, 1 for regression detected.
    """
    set_path = DATA_EVAL / f"{set_name}.jsonl"
    if not set_path.exists():
        logger.error("Eval set not found: %s", set_path)
        return 1

    records = load(set_path)
    logger.info("Loaded %d records from %s", len(records), set_path)

    per_record: list[dict] = []

    async with httpx.AsyncClient() as http_client:
        for i, record in enumerate(records, 1):
            logger.info("Evaluating record %d/%d: %s", i, len(records), record.id)
            result = await _run_record(http_client, backend, mode, record)
            per_record.append(result)

    # Compute aggregate means (skip errored records for LLM metrics)
    valid = [r for r in per_record if r["error"] is None]
    aggregate = {
        "context_precision_at_10": _mean([r["context_precision"] for r in valid]),
        "context_recall": _mean([r["context_recall"] for r in valid]),
        "faithfulness": _mean([r["faithfulness"] for r in valid]),
        "answer_relevance": _mean([r["answer_relevance"] for r in valid]),
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "set": set_name,
        "mode": mode,
        "timestamp": timestamp,
        "n": len(records),
        "n_valid": len(valid),
        "metrics": aggregate,
        "per_record": per_record,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{set_name}_{mode}_{timestamp}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Report written to %s", report_path)
    print(json.dumps(aggregate, indent=2))

    regression = _check_regression(aggregate, mode)
    return 1 if regression else 0


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Run the RAG evaluation harness.")
    parser.add_argument("--set", default="base50", help="Eval set name (without .jsonl).")
    parser.add_argument("--mode", default="tutor", help="Chat mode to evaluate.")
    parser.add_argument(
        "--backend",
        default="http://localhost:8765",
        help="Base URL of the running chat backend.",
    )
    args = parser.parse_args()
    exit_code = asyncio.run(_run(args.set, args.mode, args.backend))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
