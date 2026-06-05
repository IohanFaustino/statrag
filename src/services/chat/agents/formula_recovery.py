"""Recover OCR-dropped defining equations for gap concepts.

Per gap, in parallel: cache → vision-on-figure (search_figures + inspect_figure)
→ formula-scoped text re-query. Best-effort; returns only equations found.
"""
from __future__ import annotations

import asyncio
import logging
import re

from src.services.chat.agents.formula_cache import RecoveredEquation, cache_lookup, cache_write
from src.services.chat.agents.formula_gaps import GapConcept
from src.services.chat.retrieval import hybrid_search, search_figures
from src.services.chat.tools.inspect_figure import inspect_figure

logger = logging.getLogger(__name__)

_LATEX_RE = re.compile(r"\$\$?[^$]+?\$\$?")


def _first_latex(text: str) -> str | None:
    m = _LATEX_RE.search(text or "")
    return m.group(0) if m else None


def _cite(fig) -> str:
    book = getattr(fig, "book", "") or ""
    chap = getattr(fig, "chapter", "") or ""
    return f"{book} {chap}".strip()


async def _recover_one(query: str, gap: GapConcept) -> RecoveredEquation | None:
    # 1. cache
    try:
        hit = await cache_lookup(gap.term)
        if hit:
            return hit
    except Exception:  # noqa: BLE001
        logger.exception("cache_lookup raised for %s", gap.term)
    # 2. vision on figure
    try:
        figs = search_figures(f"{gap.term} definition formula equation",
                              book_slugs=gap.book_slugs or None, k=2)
        for fig in figs:
            txt = await inspect_figure(
                fig, query=(f"Transcribe the exact defining equation for '{gap.term}' "
                            f"shown in this figure as LaTeX, delimited with $...$ or $$...$$. "
                            f"Output ONLY the equation."))
            latex = _first_latex(txt)
            if latex:
                eq = RecoveredEquation(term=gap.term, latex=latex, citation=_cite(fig))
                await cache_write(eq.term, eq.latex, eq.citation)
                return eq
    except Exception:  # noqa: BLE001
        logger.exception("vision recovery failed for %s", gap.term)
    # 3. text re-query fallback
    try:
        srcs, _ = hybrid_search(f"{gap.term} is defined as the formula",
                                book_slugs=gap.book_slugs or None, top_k=3, rerank=False)
        for s in srcs:
            chunk = getattr(s, "chunk", "") or ""
            if gap.term.split()[0].lower() in chunk.lower():
                latex = _first_latex(chunk)
                if latex:
                    cite = f"{getattr(s,'book','')} {getattr(s,'chapter','')}".strip()
                    eq = RecoveredEquation(term=gap.term, latex=latex, citation=cite)
                    await cache_write(eq.term, eq.latex, eq.citation)
                    return eq
    except Exception:  # noqa: BLE001
        logger.exception("text fallback failed for %s", gap.term)
    return None


async def recover_formulas(query: str, gaps: list[GapConcept]) -> list[RecoveredEquation]:
    """Recover an equation per gap, in parallel. Returns only those found."""
    if not gaps:
        return []
    results = await asyncio.gather(*(_recover_one(query, g) for g in gaps), return_exceptions=True)
    return [r for r in results if isinstance(r, RecoveredEquation)]


def format_recovered_block(eqs: list[RecoveredEquation]) -> str:
    """Render the recovered equations for the synth prompt. Empty → ''."""
    if not eqs:
        return ""
    lines = ["<recovered_equations>"]
    for e in eqs:
        cite = f" [{e.citation}]" if e.citation else ""
        lines.append(f"- {e.term}: {e.latex}{cite}")
    lines.append("</recovered_equations>")
    return "\n".join(lines)
