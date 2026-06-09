"""Extension-mode agent tools: Wikipedia lookup + cross-book / peek retrieval.

Chinese-wall: imports only stdlib, httpx, langchain.tools, and (later)
src.services.chat.retrieval."""
from __future__ import annotations

import urllib.parse

import httpx
from langchain.tools import tool

_WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"


@tool
def wikipedia_lookup(query: str) -> str:
    """Fetch the lead extract of the best-matching English Wikipedia article.
    Returns the extract text followed by the article URL, or a 'no wikipedia
    result' marker. Falls back to the Wikipedia search API when the direct
    title lookup returns no match."""
    title = urllib.parse.quote(query.strip().replace(" ", "_"))

    def _get_summary(t: str):
        try:
            resp = httpx.get(
                _WIKI_SUMMARY + t,
                timeout=10.0,
                headers={"accept": "application/json"},
            )
            return resp if resp.status_code == 200 else None
        except Exception:  # noqa: BLE001
            return None

    resp = _get_summary(title)

    if resp is None:
        # Disambiguation fallback: Wikipedia search API → take first result title.
        try:
            search_resp = httpx.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "srlimit": 1,
                },
                timeout=10.0,
            )
            if search_resp.status_code == 200:
                results = search_resp.json().get("query", {}).get("search", [])
                if results:
                    fallback_title = urllib.parse.quote(
                        results[0]["title"].replace(" ", "_")
                    )
                    resp = _get_summary(fallback_title)
        except Exception:  # noqa: BLE001
            pass

    if resp is None:
        return "no wikipedia result"
    data = resp.json()
    extract = (data.get("extract") or "").strip()
    if not extract:
        return "no wikipedia result"
    url = data.get("content_urls", {}).get("desktop", {}).get("page") or ""
    return f"{extract}\n\n[source] {url}"


from src.services.chat.retrieval import hybrid_search  # noqa: E402


def _fmt_sources(rows) -> str:
    parts = []
    for r in rows:
        loc = f"{getattr(r, 'book', '?')} §{getattr(r, 'section', '?')}"
        body = getattr(r, "chunk", "") or getattr(r, "excerpt", "") or ""
        parts.append(f"[{loc}]\n{body}")
    return "\n\n---\n\n".join(parts) if parts else "no results"


def make_retrieve_corpus(
    *,
    exclude_book: str,
    all_slugs: list[str],
    seen_ids: set[str] | None = None,
):
    """Augmentor tool: cross-book retrieval EXCLUDING the base book.
    seen_ids: mutable set of chunk_ids already returned in prior rounds —
    deduped entries are skipped to prevent duplicate footnotes."""
    slugs = [s for s in all_slugs if s != exclude_book]
    _seen: set[str] = seen_ids if seen_ids is not None else set()

    @tool
    def retrieve_corpus(query: str) -> str:
        """Search OTHER books in the corpus (never the base book) for material
        that augments a gap. Returns matched passages with book/section tags."""
        # rerank=False on purpose: the cross-encoder reranker fails to load
        # inside the deepagents worker thread ("Cannot copy out of meta tensor").
        # Dense+sparse RRF gives good augmentation candidates without it.
        rows, _meta = hybrid_search(query, book_slugs=slugs, top_k=10, rerank=False)
        new_rows = []
        for r in rows:
            cid = getattr(r, "chunk_id", "") or ""
            if cid and cid in _seen:
                continue
            if cid:
                _seen.add(cid)
            new_rows.append(r)
        return _fmt_sources(new_rows)

    return retrieve_corpus


def make_retrieve_peek(*, all_slugs: list[str]):
    """Analyst tool: read-only peek across the corpus to judge what a section
    covers / is missing. Does not augment."""

    @tool
    def retrieve_peek(query: str) -> str:
        """Peek at what the corpus says about a topic (read-only, for gap
        analysis). Returns matched passages."""
        rows, _meta = hybrid_search(query, book_slugs=all_slugs, top_k=4, rerank=False)
        return _fmt_sources(rows)

    return retrieve_peek
