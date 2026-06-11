"""Citation binder — PURE CODE. Maps writer bullets (evidence_ids) to StoryCitation
objects copied verbatim from Evidence.meta. A bullet with zero valid ids is
dropped and its subject reported (→ unfilled_subjects)."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.services.chat.schemas.output import CuriosityItem, StoryCitation

from .research import Evidence


@dataclass
class BulletDraft:
    take_idx: int
    subject: str
    body: str
    evidence_ids: list[str] = field(default_factory=list)


def _label(e: Evidence) -> str:
    m = e.meta
    if e.kind == "wikipedia":
        label = m.get('title') or m.get('url') or 'Wikipedia'
        return f"Wikipedia: {label}"
    parts = [m.get("authors") or m.get("book_name") or m.get("book_slug") or "corpus"]
    if m.get("book_name") and m.get("authors"):
        parts.append(f"— {m['book_name']}")
    if m.get("section_id"):
        parts.append(f"§{m['section_id']}")
    if m.get("pages"):
        parts.append(f"pp. {m['pages']}")
    return " ".join(parts)


def _citation(e: Evidence) -> StoryCitation:
    m = e.meta
    return StoryCitation(
        kind="corpus" if e.kind == "corpus" else "wikipedia",
        label=_label(e),
        book_slug=m.get("book_slug"), book_name=m.get("book_name"),
        authors=m.get("authors"), year=m.get("year"), chapter=m.get("chapter"),
        section_id=m.get("section_id"), pages=m.get("pages"),
        title=m.get("title"), url=m.get("url"), chunk_id=m.get("chunk_id"),
    )


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
