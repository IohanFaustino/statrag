"""Shared book/chapter/section scope resolver for chapter + qa modes.

Catalog-in-prompt: the parse LLM is given a compact book catalog so fuzzy,
paraphrased, or author-only references resolve to a slug with a confidence.
Numeric section refs ("7.2 up to 7.4") are expanded deterministically here,
never left to the LLM.

Chinese-wall: imports only src.core.* and sibling src.services.chat.*.
"""
from __future__ import annotations

import json
import logging
import re

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.schemas import BookResolution, CatalogBook

logger = logging.getLogger(__name__)

_SEC = re.compile(r"\b(\d+)\.(\d+)\b")


def expand_section_refs(text: str) -> list[str]:
    """Extract section numbers, expanding "X.a up to/-/through X.b" ranges.

    Returns ordered, de-duplicated "X.y" strings. Empty if none found.
    """
    nums = _SEC.findall(text or "")
    if not nums:
        return []
    is_range = bool(re.search(r"(up to|through|to|[-–—])", text))
    pairs = [(int(a), int(b)) for a, b in nums]
    out: list[str] = []
    if is_range and len(pairs) >= 2 and pairs[0][0] == pairs[-1][0]:
        chap = pairs[0][0]
        lo, hi = pairs[0][1], pairs[-1][1]
        if lo <= hi:
            out = [f"{chap}.{i}" for i in range(lo, hi + 1)]
    if not out:
        out = [f"{a}.{b}" for a, b in pairs]
    seen: set[str] = set()
    deduped = []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped
