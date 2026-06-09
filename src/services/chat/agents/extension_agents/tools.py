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
