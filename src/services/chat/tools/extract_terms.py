"""`@tool extract_terms` — pull technical terms from arbitrary text.

Used by the ``annotate`` mode to identify glossable terms before retrieving
definitions. Nano LLM call; cheap.

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import json
import logging

import openai as _openai
from langchain_core.tools import tool

from src.core.config import settings
from src.services.chat._fences import strip_fences

logger = logging.getLogger(__name__)


@tool
def extract_terms(text: str, max_terms: int = 20) -> str:
    """Identify technical terms in a passage of prose.

    Use this when the user asks for an annotated reading or glossary. The
    returned list is a starting point — pair with :func:`retrieve` to ground
    each term in the corpus.

    Args:
        text: Source passage to scan for technical terms.
        max_terms: Maximum terms to return (1-50).

    Returns:
        A JSON string list of strings — the extracted terms, deduplicated and
        ordered by first appearance in *text*.
    """
    max_terms = max(1, min(int(max_terms), 50))
    prompt = (
        "Identify the technical terms (single words or short phrases) in the "
        "following passage that a learner might need to look up. Return ONLY "
        'a JSON array of strings, no other text. Limit: '
        f"{max_terms} terms.\n\nPassage:\n{text}"
    )
    try:
        oa = _openai.OpenAI(api_key=settings.openai_api_key)
        resp = oa.chat.completions.create(
            model=settings.openai_model_nano,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.0,
        )
        raw = strip_fences(resp.choices[0].message.content or "[]")
        terms = json.loads(raw)
        if not isinstance(terms, list):
            terms = []
    except Exception:  # noqa: BLE001
        logger.exception("extract_terms: LLM/JSON parse failed")
        terms = []
    return json.dumps([str(t) for t in terms][:max_terms], ensure_ascii=False)
