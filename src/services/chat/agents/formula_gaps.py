"""Pure detector for concepts whose defining equation is missing from the
retrieved sources because it was OCR-dropped to an image placeholder.

No I/O, no LLM — deterministic, unit-testable on fixture chunks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.services.chat.schemas import Source

# A definitional span: a definiendum followed by "is/are defined as|to be" or
# the textbook heading form "<Term> of an estimator".
_DEF_RE = re.compile(
    r"(?P<term>[A-Z][A-Za-z][A-Za-z \-]{1,40}?)\s+"
    r"(?:of an estimator|is defined as|are defined as|is defined to be|of the estimator)",
    re.IGNORECASE,
)
# Match a genuine block `$$ ... = ... $$` or inline `$ <non-ws> ... = ... $`.
# Requiring a non-whitespace char immediately after the opening `$` prevents
# the false positive `$ = prose text $` that arises when two separate inline
# math tokens ($a$ and $b$) appear on either side of a prose `=` sign.
_LATEX_RE = re.compile(r"\$\$[^$]*=[^$]*\$\$|\$[^$\s][^$]*=[^$]*\$")
_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_WINDOW = 220  # chars around the definition span to look for latex / image
_MAX_GAPS = 4


@dataclass
class GapConcept:
    term: str
    hint: str
    book_slugs: list[str] = field(default_factory=list)


def _norm(term: str) -> str:
    return re.sub(r"\s+", " ", term).strip().lower()


def detect_formula_gaps(sources: list[Source], query: str) -> list[GapConcept]:
    """Return concepts whose defining equation is absent as LaTeX but whose
    definition sits next to a dropped image placeholder (formula lost to OCR).

    Args:
        sources: Retrieved source chunks to scan.
        query: Reserved for future query-relevance filtering (Task 4 callers in
            orchestrator_workers pass the user query here); do not remove.
    """
    by_term: dict[str, GapConcept] = {}
    for s in sources:
        text = s.chunk or s.excerpt or ""
        for m in _DEF_RE.finditer(text):
            term = m.group("term").strip()
            lo = max(0, m.start() - _WINDOW)
            hi = min(len(text), m.end() + _WINDOW)
            window = text[lo:hi]
            has_latex = bool(_LATEX_RE.search(window))
            has_img = bool(_IMG_RE.search(window))
            if has_latex or not has_img:
                continue  # equation present, or no evidence it was dropped
            key = _norm(term)
            book = getattr(s, "book", "") or ""
            if key in by_term:
                if book and book not in by_term[key].book_slugs:
                    by_term[key].book_slugs.append(book)
            else:
                by_term[key] = GapConcept(term=term, hint=window.strip(),
                                          book_slugs=[book] if book else [])
    return list(by_term.values())[:_MAX_GAPS]
