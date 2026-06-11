"""Citation binder — PURE CODE. Maps writer bullets (evidence_ids) to StoryCitation
objects copied verbatim from Evidence.meta. A bullet with zero valid ids is
dropped and its subject reported (→ unfilled_subjects)."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.services.chat.schemas.output import CuriosityItem, StoryCitation

# Import shared primitives from the mode-agnostic research module.
from src.services.chat.research import Evidence, _citation, _label  # noqa: F401


@dataclass
class BulletDraft:
    take_idx: int
    subject: str
    body: str
    evidence_ids: list[str] = field(default_factory=list)


def bind_citations(
    bullets: list[BulletDraft], evidence: list[Evidence],
) -> tuple[list[tuple[int, CuriosityItem]], list[str]]:
    """Returns ([(take_idx, CuriosityItem)], dropped_subjects)."""
    by_id = {e.id: e for e in evidence}
    out: list[tuple[int, CuriosityItem]] = []
    dropped: list[str] = []
    for b in bullets:
        cits = [_citation(by_id[i]) for i in b.evidence_ids if i in by_id]
        if not cits:
            dropped.append(b.subject)
            continue
        out.append((b.take_idx,
                    CuriosityItem(subject=b.subject, body=b.body, citations=cits)))
    return out, dropped
