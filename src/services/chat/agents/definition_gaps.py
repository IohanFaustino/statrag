"""Pure detector for concepts whose definitional label is missing from the
retrieved sources because no formal definition was present.

No I/O, no LLM — deterministic, unit-testable on fixture chunks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.services.chat.schemas import Source

# Regex for definitional intent in the query
# matches any of the words/phrases: "what is", "what are", "define", "definition of",
# "forms of", "form of", "strict", "weak", "stationar"
# Note: "stationar" is matched without word boundary to catch "stationarity" etc.
_DEFINITIONAL_RE = re.compile(
    r"\b(what\s+is|what\s+are|define|definition\s+of|forms\s+of|form\s+of)\b|"
    r"\b(strict|weak)\b|"
    r"stationar",
    re.IGNORECASE,
)

# Regex for labelled/formal definition in a source chunk
# matches either:
# - "Definition\s+\d+(\.\d+)*" (e.g., "Definition 14.1", "Definition 1.2.3")
# - "is\s+(strictly|weakly|covariance)\b" (e.g., "is strictly stationary")
# - "is\s+said\s+to\s+be" (e.g., "is said to be")
_LABELLED_DEF_RE = re.compile(
    r"(Definition\s+\d+(\.\d+)*|is\s+(strictly|weakly|covariance)\b|is\s+said\s+to\s+be)",
    re.IGNORECASE,
)


@dataclass
class DefinitionGap:
    concept: str
    norm: str
    book_slugs: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _query_is_definitional(query: str) -> bool:
    return bool(_DEFINITIONAL_RE.search(query))


def _has_labelled_def(concept: str, sources: list[Source]) -> bool:
    """True if ANY source whose chunk/excerpt mentions the concept's first word
    (case-insensitive) ALSO contains a labelled definition pattern.
    """
    if not concept:
        return False
    # Get the first word of the concept
    first_word = concept.split()[0].lower() if concept.split() else ""
    if not first_word:
        return False

    for s in sources:
        text = s.chunk or s.excerpt or ""
        if not first_word in text.lower():
            continue
        if _LABELLED_DEF_RE.search(text):
            return True
    return False


_MAX_GAPS = 3


def detect_definition_gaps(
    concepts: list[str], query: str, sources: list[Source]
) -> list[DefinitionGap]:
    """Return concepts that need definition retrieval because:
    - the query is definitional (contains definitional keywords)
    - and the concept lacks a labelled/formal definition in the sources.
    """
    if not _query_is_definitional(query):
        return []

    by_norm: dict[str, DefinitionGap] = {}
    for concept in concepts:
        if not concept or not concept.strip():
            continue
        norm = _norm(concept)
        if norm in by_norm:
            continue
        if not _has_labelled_def(concept, sources):
            by_norm[norm] = DefinitionGap(
                concept=concept.strip(), norm=norm, book_slugs=[]
            )

    # Dedupe by norm, cap at _MAX_GAPS
    result = list(by_norm.values())[:_MAX_GAPS]
    return result
