"""Pure-code helpers for definition-recovery (no network / LLM calls).

Async orchestration lives elsewhere; this module provides only deterministic
utilities: token-recall scoring, verbatim detection, formal-statement binding,
and text-block formatting.
"""
from __future__ import annotations

import re

from src.services.chat.agents.definition_cache import RecoveredDefinition
from src.services.chat.schemas import Source
from src.services.chat.schemas.output import TutorFormalDef

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