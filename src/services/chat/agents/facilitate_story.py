"""Facilitate story mode — single-section narrative pipeline.

Pure-code binders/fidelity here; the LLM runner lands in run_facilitate_story
(added in a later task). Chinese-wall: imports only src.core.* and sibling
src.services.chat.*.
"""
from __future__ import annotations

import re

from src.services.chat.schemas.output import ConceptAnchor

_MARKER = re.compile(r"\[\[(c\d+)\]\]")


def referenced_ids(text: str) -> set[str]:
    return set(_MARKER.findall(text or ""))


def strip_unbound_markers(text: str, *, valid_ids: set[str]) -> str:
    """Remove [[cN]] markers whose id is not in valid_ids; keep surrounding text."""
    def repl(m: re.Match) -> str:
        return m.group(0) if m.group(1) in valid_ids else ""
    return _MARKER.sub(repl, text or "")


def bind_concepts(anchors: list[ConceptAnchor], *, referenced_ids: set[str]) -> list[ConceptAnchor]:
    """Keep only anchors actually referenced by a surviving [[cN]] marker."""
    return [a for a in anchors if a.id in referenced_ids]


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\$+", " ", s)             # drop math delimiters
    s = re.sub(r"[^a-z0-9\\ ]+", " ", s)   # keep latex backslash words + alnum
    return re.sub(r"\s+", " ", s).strip()


def statement_fidelity(statement: str, source_text: str) -> tuple[bool, float]:
    """Fuzzy token-recall of the formal statement against the source section.
    True when most statement tokens appear in the source (verbatim/near-verbatim)."""
    st = set(_norm(statement).split())
    src = set(_norm(source_text).split())
    if len(st) < 4:        # too short to be a credible formal statement
        return False, 0.0
    recall = len(st & src) / len(st)
    return recall >= 0.6, recall
