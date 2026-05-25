"""LLM cost estimator + per-call cost log (data/cost_log.jsonl)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.core.config import DATA_DIR

logger = logging.getLogger(__name__)
COST_LOG_PATH: Path = DATA_DIR / "cost_log.jsonl"

# USD per 1M tokens — keep conservative estimates; revisit when actual prices drift.
PRICE_PER_1M: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o":                    {"in": 2.50, "out": 10.00},
    "gpt-4o-mini":               {"in": 0.15, "out": 0.60},
    "gpt-5.4-nano-2026-03-17":   {"in": 0.10, "out": 0.40},
    "gpt-5.4-2026-03-05":        {"in": 5.00, "out": 15.00},
    # DeepSeek
    "deepseek-chat":             {"in": 0.27, "out": 1.10},
    "deepseek-reasoner":         {"in": 0.55, "out": 2.20},
    "deepseek-v4-pro":           {"in": 0.55, "out": 2.20},
    # Groq
    "meta-llama/llama-4-scout-17b-16e-instruct": {"in": 0.11, "out": 0.34},
    "llama-3.3-70b-versatile":                   {"in": 0.59, "out": 0.79},
    "openai/gpt-oss-120b":                       {"in": 0.15, "out": 0.75},
    "openai/gpt-oss-20b":                        {"in": 0.10, "out": 0.50},
    # Vision (treat input image tiles as ~700 tokens each at gpt-4o rate)
    "gpt-4o-vision":             {"in": 2.50, "out": 10.00, "per_image": 0.001},
    # Embeddings
    "text-embedding-3-large":    {"in": 0.13, "out": 0.0},
}


def usd_est(
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    images: int = 0,
) -> float:
    """Estimate USD cost for a model call.

    Args:
        model: Model identifier string.
        input_tokens: Number of prompt tokens consumed.
        output_tokens: Number of completion tokens generated.
        images: Number of image tiles passed (vision models only).

    Returns:
        Estimated cost in USD, or 0.0 if the model is not in the price table.
    """
    p = PRICE_PER_1M.get(model)
    if not p:
        return 0.0
    cost = (input_tokens / 1_000_000) * p["in"] + (output_tokens / 1_000_000) * p["out"]
    if images and "per_image" in p:
        cost += images * p["per_image"]
    return cost


def log_call(
    *,
    model: str,
    purpose: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    images: int = 0,
    latency_ms: int | None = None,
    extra: dict | None = None,
) -> None:
    """Append a cost log row to ``data/cost_log.jsonl``. Best-effort; never raises.

    Args:
        model: Model identifier used for the call.
        purpose: Short description of the call purpose (e.g. ``"inspect_figure"``).
        input_tokens: Number of prompt tokens consumed.
        output_tokens: Number of completion tokens generated.
        images: Number of image tiles passed (vision models only).
        latency_ms: Wall-clock latency in milliseconds, if measured.
        extra: Optional extra fields to merge into the log row.
    """
    try:
        COST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "purpose": purpose,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "images": images,
            "latency_ms": latency_ms,
            "usd_est": usd_est(
                model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                images=images,
            ),
            **(extra or {}),
        }
        with open(COST_LOG_PATH, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        logger.warning("cost log write failed", exc_info=True)
