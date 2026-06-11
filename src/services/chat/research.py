"""Shared research primitives — PURE CODE (no LLM).

Mode-agnostic building blocks used by both Extension v2 and the Q&A deepagent:
- Evidence dataclass
- corpus_evidence — cross-book hybrid search, verbatim payload meta
- wiki_evidence   — Wikipedia REST summary + search-API fallback
- _wiki_summary_json — internal helper (exposed for patching in tests)
- _label, _citation — StoryCitation constructors from Evidence

Chinese-wall note: imports only src.core.* and sibling src.services.chat.*.
Never imports tutor modules (deep_tutor, orchestrator_workers, ow_*, prompts/deep_tutor).
"""
from __future__ import annotations

import logging
import os
import threading
import urllib.parse
import uuid
from dataclasses import dataclass, field

import httpx

from src.services.chat.retrieval import hybrid_search
from src.services.chat.schemas.output import StoryCitation

# Wikipedia robot policy requires an identifying User-Agent header; requests
# without one return HTTP 403 "Please set a user-agent".  Both the REST summary
# endpoint and the search API (w/api.php) enforce this requirement.
_WIKI_HEADERS = {
    "accept": "application/json",
    # Wikipedia robot policy requires an identifying User-Agent (403 without).
    "user-agent": "statrag-extension/2.0 (local RAG research tool; contact: local)",
}

# graph._research_subject fans out corpus_evidence calls via asyncio.to_thread,
# so multiple threads share the same seen_ids set concurrently.  Without a lock
# the check-then-add (cid in seen_ids / seen_ids.add) is a TOCTOU race: two
# threads can both pass the membership check before either adds the id, allowing
# the same chunk to appear twice in the evidence list.
_seen_lock = threading.Lock()

_logger = logging.getLogger(__name__)

_WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
_WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"


@dataclass
class Evidence:
    subject_id: str
    kind: str                      # "corpus" | "wikipedia"
    text: str
    meta: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


def corpus_evidence(query: str, *, subject_id: str, exclude_book: str,
                    all_slugs: list[str], seen_ids: set[str],
                    top_n: int = 4) -> list[Evidence]:
    """Cross-book hybrid search (rerank ON), payload meta copied verbatim."""
    slugs = [s for s in all_slugs if s != exclude_book]
    if not slugs:
        return []
    try:
        floor = float(os.environ.get("EXTENSION_MIN_SCORE", "0"))
    except ValueError:
        floor = 0.0
    try:
        rows, _ = hybrid_search(query, book_slugs=slugs, top_k=top_n,
                                rerank=True, rerank_top_n=top_n)
    except Exception:  # noqa: BLE001 — retrieval failure degrades to no evidence
        _logger.exception("corpus_evidence: hybrid_search failed for subject_id=%r", subject_id)
        return []
    out: list[Evidence] = []
    for r in rows:
        # Real Source uses `chunkId`; plan-name fallback for legacy fixtures/mocks.
        cid = getattr(r, "chunkId", None) or getattr(r, "chunk_id", None) or ""
        if cid:
            with _seen_lock:
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
        if floor and (getattr(r, "score", 0) or 0) < floor:
            continue
        pf, pt = getattr(r, "page_from", None), getattr(r, "page_to", None)
        pages = f"{pf}–{pt}" if pf and pt and pf != pt else (str(pf) if pf else None)
        # Real Source: book/chapter; plan-name fallbacks for legacy.
        book_slug = getattr(r, "book", None) or getattr(r, "book_slug", None)
        chapter = getattr(r, "chapter", None) or getattr(r, "chapter_id", None)
        out.append(Evidence(
            subject_id=subject_id, kind="corpus",
            text=getattr(r, "chunk", "") or getattr(r, "excerpt", "") or "",
            meta={
                "book_slug": book_slug,
                "book_name": getattr(r, "book_name", None),
                "authors": getattr(r, "authors", None),
                "year": getattr(r, "year", None),
                "chapter": chapter,
                "section_id": getattr(r, "section", None),
                "pages": pages,
                "chunk_id": cid or None,
            }))
    return out


def _wiki_summary_json(query: str) -> dict | None:
    """REST summary for best-matching article; search-API fallback on miss."""
    def _get(title: str) -> dict | None:
        try:
            r = httpx.get(_WIKI_SUMMARY + urllib.parse.quote(title.replace(" ", "_")),
                          timeout=10.0, headers=_WIKI_HEADERS)
            return r.json() if r.status_code == 200 else None
        except Exception:  # noqa: BLE001
            _logger.debug("_wiki_summary_json: summary fetch failed for title=%r", title)
            return None

    data = _get(query.strip())
    if data is None:
        try:
            sr = httpx.get(_WIKI_SEARCH, timeout=10.0, headers=_WIKI_HEADERS, params={
                "action": "query", "list": "search", "srsearch": query,
                "format": "json", "srlimit": 1})
            hits = sr.json().get("query", {}).get("search", []) if sr.status_code == 200 else []
            if hits:
                data = _get(hits[0]["title"])
        except Exception:  # noqa: BLE001
            _logger.debug("_wiki_summary_json: search-API fallback failed for query=%r", query)
            data = None
    return data


def wiki_evidence(query: str, *, subject_id: str) -> list[Evidence]:
    data = _wiki_summary_json(query)
    if not data or not data.get("extract"):
        return []
    url = (data.get("content_urls", {}).get("desktop", {}) or {}).get("page", "")
    return [Evidence(subject_id=subject_id, kind="wikipedia", text=data["extract"],
                     meta={"title": data.get("title", query), "url": url})]


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
