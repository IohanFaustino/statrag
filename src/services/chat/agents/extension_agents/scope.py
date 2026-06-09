"""Deterministic structural shell for extension mode: resolve book+chapter,
clarify gate, and lay ordered sections out as /structure files.

Chinese-wall: reuses shared _scope + schemas; no tutor/qa imports."""
from __future__ import annotations

from src.services.chat.agents._scope import maybe_clarify, resolve_book
from src.services.chat.schemas import BookResolution, CatalogBook


async def aresolve_scope_or_clarify(message: str, *, catalog: list[CatalogBook],
                                    selected_slugs: list[str]):
    """Return (clarify_dict_or_None, BookResolution_or_None). When the book is
    ambiguous, returns (clarify, None) — the runner must surface it and stop
    before any agentic spend (the common-ground gate)."""
    res: BookResolution = await resolve_book(
        message, selected_slugs=selected_slugs, catalog=catalog)
    clar = maybe_clarify(res, catalog)
    if clar is not None:
        return clar, None
    return None, res


def build_structure_files(sections: list[dict]) -> dict[str, str]:
    """Lay out already-ordered sections as /structure/NN_<id>.md virtual files.
    Order is preserved from the input (the caller fetches them in chapter order).
    Each section dict has keys: section_id, h2_path, text."""
    files: dict[str, str] = {}
    for i, s in enumerate(sections):
        sid = str(s.get("section_id", i)).replace("/", "-")
        path = f"/structure/{i:02d}_{sid}.md"
        head = f"# {s.get('h2_path', sid)}\n\n"
        files[path] = head + (s.get("text") or "")
    return files
