"""Pure-code helpers for definition-recovery (no network / LLM calls).

Async orchestration lives elsewhere; this module provides only deterministic
utilities: token-recall scoring, verbatim detection, formal-statement binding,
and text-block formatting.
"""
from __future__ import annotations

import re

import asyncio
import logging
from pydantic import BaseModel

from src.services.chat.agents.definition_cache import RecoveredDefinition, cache_lookup, cache_write
from src.services.chat.agents.definition_gaps import DefinitionGap
from src.services.chat.retrieval import hybrid_search
from src.services.chat.schemas import Source
from src.services.chat.schemas.output import TutorFormalDef

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> set[str]:
    """Lowercase word-tokens of *s* (letters + digits only)."""
    return set(_WORD_RE.findall(s.lower()))


# ---------------------------------------------------------------------------
# Recall & verbatim check
# ---------------------------------------------------------------------------

_RECALL_THRESHOLD = 0.85


def definition_recall(statement: str, source_text: str) -> float:
    """Token-level recall of *statement* tokens inside *source_text*.

    Returns ``0.0`` when *statement* has no tokens (guards division by zero).
    """
    stmt_toks = _tokens(statement)
    if not stmt_toks:
        return 0.0
    src_toks = _tokens(source_text)
    return len(stmt_toks & src_toks) / len(stmt_toks)


def is_verbatim(statement: str, source_text: str) -> bool:
    """True when *statement* shares ≥ ``_RECALL_THRESHOLD`` of its tokens with *source_text*."""
    return definition_recall(statement, source_text) >= _RECALL_THRESHOLD


# ---------------------------------------------------------------------------
# Formal-statement binder
# ---------------------------------------------------------------------------

def build_formal_statements(
    recovered: list[RecoveredDefinition],
    sources: list[Source],
) -> list[TutorFormalDef]:
    """Pure-code true-by-construction bind of recovered definitions to source ranks.

    Only emits a ``TutorFormalDef`` when the source list contains the matching
    ``chunkId`` *and* the recovered statement is non-empty.  This keeps citations
    honest — every ``cite`` number maps back to a real retrieval result.
    """
    rankmap: dict[str, int] = {s.chunkId: s.rank for s in sources}
    out: list[TutorFormalDef] = []
    for rd in recovered:
        cite = rankmap.get(rd.chunkId, 0)
        if cite <= 0 or not rd.statement.strip():
            continue
        out.append(
            TutorFormalDef(
                kind=rd.kind or "definition",
                label=rd.label,
                statement=rd.statement,
                cite=cite,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Definitions text block
# ---------------------------------------------------------------------------

def format_definitions_block(recovered: list[RecoveredDefinition]) -> str:
    """Render recovered definitions as a fenced XML block for prompt injection.

    Returns an empty string when *recovered* is empty.
    """
    if not recovered:
        return ""
    lines = ["<formal_definitions>"]
    for rd in recovered:
        head = rd.label or rd.kind
        lines.append(f"- {head} ({rd.concept}): {rd.statement}")
    lines.append("</formal_definitions>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Async LLM-assisted recovery
# ---------------------------------------------------------------------------

_EXTRACT_MODEL = "deepseek-v4-flash"


class _ExtractedDef(BaseModel):
    found: bool = False
    kind: str = "definition"
    label: str = ""
    statement: str = ""


_EXTRACT_SYS = (
    "You extract a FORMAL definition or theorem from a textbook chunk, VERBATIM. "
    "If the chunk states an explicit formal definition/theorem for the concept, set found=true and copy it "
    "WORD FOR WORD into 'statement' (include its label e.g. 'Definition 14.1' in 'label', and any $$math$$). "
    "Do NOT paraphrase or summarize. If the chunk has no formal definition, set found=false. "
    "kind is one of definition/theorem/proposition/lemma/corollary."
)


async def _extract_verbatim(concept: str, chunk_text: str, model: str = _EXTRACT_MODEL) -> "_ExtractedDef | None":
    from src.services.chat.llm.router import aclient_for  # noqa: PLC0415
    from src.services.chat.llm.structured import apply_structured_output  # noqa: PLC0415
    messages = [{"role": "system", "content": _EXTRACT_SYS},
                {"role": "user", "content": f"Concept: {concept}\n\nChunk:\n{chunk_text[:4000]}"}]
    try:
        oa = aclient_for(model)
        messages, response_format = apply_structured_output(messages, model, _ExtractedDef)
        kwargs = {"model": model, "messages": messages, "temperature": 0.0, "max_completion_tokens": 1200}
        if response_format is not None:
            kwargs["response_format"] = response_format
        resp = await oa.chat.completions.create(**kwargs)
        return _ExtractedDef.model_validate_json(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        logger.exception("definition extract failed for %s", concept)
        return None


_KINDS = {"definition", "theorem", "proposition", "lemma", "corollary"}

# ---------------------------------------------------------------------------
# DR-8b: Placeholder penalty — penalise chunks containing OCR image
# placeholders like ![image](...) so clean-text candidates are preferred.
# ---------------------------------------------------------------------------

_IMAGE_PLACEHOLDER_RE = re.compile(r"!\[image\]\([^)]*\)", re.IGNORECASE)


def _placeholder_penalty(text: str) -> float:
    """Return a negative score proportional to the number of ``![image](…)``
    placeholders in *text*.  Clean text scores ``0.0``; each placeholder
    adds ``-0.15`` so that a chunk with many placeholders is deprioritised
    relative to a clean-text chunk covering the same concept.
    """
    n = len(_IMAGE_PLACEHOLDER_RE.findall(text))
    return -0.15 * n


async def _recover_one(query: str, gap: DefinitionGap, books: "list[str] | None") -> "RecoveredDefinition | None":
    try:
        hit = await cache_lookup(gap.concept)
        if hit:
            return hit
    except Exception:  # noqa: BLE001
        logger.exception("def cache_lookup raised for %s", gap.concept)
    try:
        srcs, _ = hybrid_search(f"formal definition of {gap.concept}", book_slugs=books, top_k=5, rerank=False)
    except Exception:  # noqa: BLE001
        logger.exception("def retrieval failed for %s", gap.concept)
        return None

    # DR-8b: sort candidates so clean-text chunks are tried before OCR-heavy ones
    scored_srcs = []
    for s in srcs:
        chunk = getattr(s, "chunk", "") or getattr(s, "excerpt", "") or ""
        penalty = _placeholder_penalty(chunk)
        scored_srcs.append((penalty, s, chunk))
    scored_srcs.sort(key=lambda t: t[0], reverse=True)  # highest (least negative) first

    for _penalty, s, chunk in scored_srcs:
        if not chunk:
            continue
        ex = await _extract_verbatim(gap.concept, chunk)
        if not ex or not ex.found or not ex.statement.strip():
            continue
        if not is_verbatim(ex.statement, chunk):   # fidelity gate (pure code, defined above)
            continue
        rd = RecoveredDefinition(
            concept=gap.concept,
            kind=ex.kind if ex.kind in _KINDS else "definition",
            label=ex.label, statement=ex.statement,
            book=getattr(s, "book", "") or "", book_name=getattr(s, "book_name", "") or "",
            chapter=getattr(s, "chapter", "") or "", section=getattr(s, "section", "") or "",
            page_from=getattr(s, "page_from", None), page_to=getattr(s, "page_to", None),
            chunkId=getattr(s, "chunkId", "") or "")
        try:
            await cache_write(rd)
        except Exception:  # noqa: BLE001
            logger.exception("def cache_write raised for %s", gap.concept)
        return rd
    return None


async def recover_definitions(query: str, gaps: "list[DefinitionGap]", books: "list[str] | None" = None) -> "list[RecoveredDefinition]":
    if not gaps:
        return []
    results = await asyncio.gather(*(_recover_one(query, g, books) for g in gaps), return_exceptions=True)
    return [r for r in results if isinstance(r, RecoveredDefinition)]