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


_MAX_ASKS = 5


def multi_question_split(prompt: str) -> list[str]:
    """Split a prompt into sentence-final-``?`` questions. Single-question or
    no-``?`` prompts return ``[prompt.strip()]``. Pure, deterministic."""
    if not prompt or not prompt.strip():
        return []
    parts = re.findall(r"[^?]*\?", prompt)
    asks = [p.strip() for p in parts if p.strip()]
    if len(asks) <= 1:
        return [prompt.strip()]
    return asks[:_MAX_ASKS]


_SCAFFOLD_RE = re.compile(
    r"^\s*(what\s+is|what\s+are|what\s+does|define|definition\s+of|explain|describe|"
    r"how\s+is|how\s+does)\s+", re.IGNORECASE)
_ARTICLE_RE = re.compile(r"^(a|an|the)\s+", re.IGNORECASE)


def concepts_from_asks(asks: list[str]) -> list[str]:
    """Best-effort bare subject of each ask (pure regex). Order preserved."""
    out: list[str] = []
    for ask in asks:
        s = _SCAFFOLD_RE.sub("", ask.strip())
        s = s.rstrip("?.!").strip()
        s = _ARTICLE_RE.sub("", s).strip()
        if s and s.lower() not in (c.lower() for c in out):
            out.append(s)
    return out


def augment_concepts_and_facets(
    query: str, concepts: list[str], facets: list[str]
) -> tuple[list[str], list[str]]:
    """For a multi-question prompt, union each question's subject into concepts
    (ask-subjects FIRST so they survive the _MAX_GAPS cap) and each question
    into facets. Single-question prompts: just ensure the subject is present."""
    asks = multi_question_split(query)
    ask_concepts = concepts_from_asks(asks)

    def _dedup(seq: list[str]) -> list[str]:
        seen: dict[str, str] = {}
        for x in seq:
            k = x.strip().lower()
            if x.strip() and k not in seen:
                seen[k] = x.strip()
        return list(seen.values())

    new_concepts = _dedup([*ask_concepts, *concepts])
    new_facets = _dedup([*facets, *asks]) if len(asks) > 1 else _dedup(facets)
    return new_concepts, new_facets


_MAX_GAPS = 5

# ---------------------------------------------------------------------------
# DR-8c: Generic concept expansion — expand umbrella terms into the specific
# named forms that appear in textbooks.  This ensures the dedicated recovery
# search looks for the exact named definitions (strict/weak/covariance
# stationarity, etc.) rather than the generic umbrella term.
# ---------------------------------------------------------------------------

_GENERIC_EXPANSIONS: dict[str, list[str]] = {
    "stationarity": ["strict stationarity", "weak stationarity", "covariance stationarity"],
    "stationary": ["strict stationarity", "weak stationarity", "covariance stationarity"],
}


def _expand_concept(concept: str) -> list[str]:
    """Expand a concept into its specific named forms.

    If *concept* is a generic umbrella term (e.g. ``"stationarity"``),
    return the list of specific forms (``["strict stationarity",
    "weak stationarity", "covariance stationarity"]``).  Otherwise return
    ``[concept]`` unchanged.
    """
    norm = concept.strip().lower()
    return _GENERIC_EXPANSIONS.get(norm, [concept])


def detect_definition_gaps(
    concepts: list[str], query: str, sources: list[Source]
) -> list[DefinitionGap]:
    """Return concepts that need definition retrieval because:
    - the query is definitional (contains definitional keywords)
    - and the concept lacks a labelled/formal definition in the sources.

    DR-8c: Generic concepts like "stationarity" are expanded into their
    specific named forms ("strict stationarity", "weak stationarity",
    "covariance stationarity") so the recovery pipeline searches for the
    exact textbook definitions. Expanded forms that came FROM a
    `_GENERIC_EXPANSIONS` entry are PREMIUM: they bypass
    `_has_labelled_def` and are always treated as gaps (spec: "premium
    concepts are always considered"). Non-expanded concepts (caller
    passed in an already-specific form) keep the existing suppression
    behavior — they remain gaps only when `_has_labelled_def` is False.
    """
    if not _query_is_definitional(query):
        return []

    # DR-8c: build (concept, is_premium) pairs. A concept is premium iff
    # its lowercase-stripped form is a KEY in _GENERIC_EXPANSIONS, in
    # which case each of its expansion values is premium. Non-keys
    # produce a single non-premium entry (themselves).
    pairs: list[tuple[str, bool]] = []
    for concept in concepts:
        if not concept or not concept.strip():
            continue
        norm0 = concept.strip().lower()
        forms = _GENERIC_EXPANSIONS.get(norm0)
        if forms:
            for f in forms:
                pairs.append((f, True))      # premium: always a gap
        else:
            pairs.append((concept.strip(), False))

    by_norm: dict[str, DefinitionGap] = {}
    for concept, is_premium in pairs:
        if not concept or not concept.strip():
            continue
        norm = _norm(concept)
        if norm in by_norm:
            continue
        if is_premium or not _has_labelled_def(concept, sources):
            by_norm[norm] = DefinitionGap(concept=concept.strip(), norm=norm, book_slugs=[])

    # Dedupe by norm, cap at _MAX_GAPS
    result = list(by_norm.values())[:_MAX_GAPS]
    return result
