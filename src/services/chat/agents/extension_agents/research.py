"""Extension v2 researcher — PURE CODE (no LLM).

Turns a subject query into Evidence objects whose ``meta`` is copied verbatim
from retrieval payloads (corpus) or the Wikipedia REST summary (wikipedia).
The citation binder later builds Citation objects ONLY from these metas, which
is what makes extension citations verifiable by construction."""
from __future__ import annotations

import os
import urllib.parse
import uuid
from dataclasses import dataclass, field

import httpx

from src.services.chat.retrieval import hybrid_search

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
    floor = float(os.environ.get("EXTENSION_MIN_SCORE", "0"))
    try:
        rows, _ = hybrid_search(query, book_slugs=slugs, top_k=top_n,
                                rerank=True, rerank_top_n=top_n)
    except Exception:  # noqa: BLE001 — retrieval failure degrades to no evidence
        return []
    out: list[Evidence] = []
    for r in rows:
        cid = getattr(r, "chunk_id", "") or ""
        if cid and cid in seen_ids:
            continue
        if floor and (getattr(r, "score", 0) or 0) < floor:
            continue
        if cid:
            seen_ids.add(cid)
        pf, pt = getattr(r, "page_from", None), getattr(r, "page_to", None)
        pages = f"{pf}–{pt}" if pf and pt and pf != pt else (str(pf) if pf else None)
        out.append(Evidence(
            subject_id=subject_id, kind="corpus",
            text=getattr(r, "chunk", "") or getattr(r, "excerpt", "") or "",
            meta={
                "book_slug": getattr(r, "book_slug", None),
                "book_name": getattr(r, "book_name", None),
                "authors": getattr(r, "authors", None),
                "year": getattr(r, "year", None),
                "chapter": getattr(r, "chapter_id", None),
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
                          timeout=10.0, headers={"accept": "application/json"})
            return r.json() if r.status_code == 200 else None
        except Exception:  # noqa: BLE001
            return None

    data = _get(query.strip())
    if data is None:
        try:
            sr = httpx.get(_WIKI_SEARCH, timeout=10.0, params={
                "action": "query", "list": "search", "srsearch": query,
                "format": "json", "srlimit": 1})
            hits = sr.json().get("query", {}).get("search", []) if sr.status_code == 200 else []
            if hits:
                data = _get(hits[0]["title"])
        except Exception:  # noqa: BLE001
            data = None
    return data


def wiki_evidence(query: str, *, subject_id: str) -> list[Evidence]:
    data = _wiki_summary_json(query)
    if not data or not data.get("extract"):
        return []
    url = (data.get("content_urls", {}).get("desktop", {}) or {}).get("page", "")
    return [Evidence(subject_id=subject_id, kind="wikipedia", text=data["extract"],
                     meta={"title": data.get("title", query), "url": url})]
