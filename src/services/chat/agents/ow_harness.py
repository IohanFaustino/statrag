"""Harness-level scaffold for the orchestrator-workers stage (ablation pilot).

TUTOR_OW_HARNESS selects the level:
  0 = baseline (current behavior, no harness) — default and fallback
  1 = observability (LangSmith tracing; behavior identical)
  2 = structured context via deepagents shared FS   (Plan B)
  3 = full deepagents orchestration                 (Plan B)

Levels 0-3 implemented (Plan B); level 4 reserved.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

_MAX_IMPLEMENTED_LEVEL = 3  # 0/1 shipped (Plan A); 2/3 degrade to 0 until Plan B


def ow_harness_level() -> int:
    """Parse TUTOR_OW_HARNESS; out-of-range / unimplemented / junk -> 0 (safe)."""
    raw = os.environ.get("TUTOR_OW_HARNESS", "0").strip()
    try:
        n = int(raw)
    except ValueError:
        return 0
    if n < 0 or n > _MAX_IMPLEMENTED_LEVEL:
        return 0
    return n


_F = TypeVar("_F", bound=Callable)


def maybe_traced(fn: _F, *, name: str) -> _F:
    """Wrap *fn* with LangSmith @traceable when level>=1 AND LANGSMITH_API_KEY is
    set. Otherwise return *fn* unchanged. Tracing NEVER changes behavior; on any
    import/wrap failure, return *fn* unchanged."""
    if ow_harness_level() < 1 or not os.environ.get("LANGSMITH_API_KEY"):
        return fn
    try:
        from langsmith import traceable
        return traceable(name=name)(fn)  # type: ignore[return-value]
    except Exception:  # noqa: BLE001
        logger.exception("LangSmith tracing wrap failed; running untraced")
        return fn


import json as _json


def structured_briefs_block(briefs) -> str:
    """Render briefs as a JSON block (the L2 structured handoff)."""
    data = [{"author": b.author, "summary": b.summary,
             "key_points": list(b.key_points), "source_ranks": list(b.source_ranks)}
            for b in briefs]
    return "<author_briefs_json>\n" + _json.dumps(data, ensure_ascii=False) + "\n</author_briefs_json>"


_NO_INFO_MARKERS = ("not discuss", "does not", "no mention", "not address",
                    "do not discuss", "doesn't", "no information")


def content_bearing(briefs) -> list:
    """Drop 'no-info' briefs (summary disclaims content or empty key_points)."""
    out = []
    for b in briefs:
        s = (b.summary or "").lower()
        if not b.key_points and not b.summary:
            continue
        if any(m in s for m in _NO_INFO_MARKERS) and len(b.key_points) == 0:
            continue
        out.append(b)
    return out
