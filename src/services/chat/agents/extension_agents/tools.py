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
    result' marker. Use to augment a section gap from Wikipedia."""
    title = urllib.parse.quote(query.strip().replace(" ", "_"))
    try:
        resp = httpx.get(_WIKI_SUMMARY + title, timeout=10.0,
                         headers={"accept": "application/json"})
    except Exception as exc:  # noqa: BLE001
        return f"no wikipedia result ({type(exc).__name__})"
    if resp.status_code != 200:
        return "no wikipedia result"
    data = resp.json()
    extract = (data.get("extract") or "").strip()
    if not extract:
        return "no wikipedia result"
    url = (data.get("content_urls", {}).get("desktop", {}).get("page") or "")
    return f"{extract}\n\n[source] {url}"


from src.services.chat.retrieval import hybrid_search  # noqa: E402


def _fmt_sources(rows) -> str:
    parts = []
    for r in rows:
        loc = f"{getattr(r, 'book', '?')} §{getattr(r, 'section', '?')}"
        body = getattr(r, "chunk", "") or getattr(r, "excerpt", "") or ""
        parts.append(f"[{loc}]\n{body}")
    return "\n\n---\n\n".join(parts) if parts else "no results"


def make_retrieve_corpus(*, exclude_book: str, all_slugs: list[str]):
    """Augmentor tool: cross-book retrieval EXCLUDING the base book."""
    slugs = [s for s in all_slugs if s != exclude_book]

    @tool
    def retrieve_corpus(query: str) -> str:
        """Search OTHER books in the corpus (never the base book) for material
        that augments a gap. Returns matched passages with book/section tags."""
        rows, _meta = hybrid_search(query, book_slugs=slugs, top_k=6, rerank=True, rerank_top_n=6)
        return _fmt_sources(rows)

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
