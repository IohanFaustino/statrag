"""Concept explorer — stateless side-chat for one concept (corpus + Wikipedia).

NEVER reads or writes the conversation message store: the side-chat cannot leak
into the main answer (true-by-construction isolation).
Chinese-wall: imports only src.core.* and sibling src.services.chat.*.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from src.core.config import settings
from src.services.chat.books import parse_catalog
from src.services.chat.llm.router import aclient_for
from src.services.chat.prompts.chapter import FACILITATE_BRIEF_PROMPT
from src.services.chat.research import corpus_evidence, wiki_evidence, _citation, Evidence

logger = logging.getLogger(__name__)


async def _brief(term: str, evidence: list[Evidence], *, model: str) -> str:
    corpus = "\n".join(e.text for e in evidence if e.kind == "corpus")[:1500]
    wiki = "\n".join(e.text for e in evidence if e.kind == "wikipedia")[:1500]
    user = f"concept: {term}\n\ncorpus passage(s):\n{corpus}\n\nwikipedia:\n{wiki}"
    oa = aclient_for(model)
    resp = await oa.chat.completions.create(model=model, temperature=0.0,
        max_completion_tokens=160,
        messages=[{"role": "system", "content": FACILITATE_BRIEF_PROMPT},
                  {"role": "user", "content": user}])
    return (resp.choices[0].message.content or "").strip()


async def concept_explore(body: dict) -> AsyncIterator[dict]:
    term = (body.get("term") or "").strip()
    history = body.get("history") or []
    model = settings.openai_model_nano
    if not term:
        yield {"type": "concept_seed", "term": term, "brief": "", "citations": []}
        yield {"type": "done"}
        return

    all_slugs = [c.slug for c in parse_catalog()]
    follow = ""
    if history:
        last = history[-1]
        follow = last.get("text", "") if last.get("role") == "user" else ""
    query = f"{term} {follow}".strip()
    seen: set[str] = set()
    try:
        corpus, wiki = await asyncio.gather(
            asyncio.to_thread(corpus_evidence, query, subject_id=term, exclude_book="",
                              all_slugs=all_slugs, seen_ids=seen, top_n=3),
            asyncio.to_thread(wiki_evidence, query, subject_id=term))
    except Exception:  # noqa: BLE001
        logger.exception("concept_explore retrieval failed")
        corpus, wiki = [], []
    evidence = list(corpus) + list(wiki)
    try:
        brief = await _brief(term, evidence, model=model)
    except Exception:  # noqa: BLE001
        logger.exception("concept_explore brief failed")
        brief = (wiki[0].text[:240] if wiki else (corpus[0].text[:240] if corpus else ""))
    citations = [_citation(e).model_dump(exclude_none=True) for e in evidence]
    event_type = "concept_followup" if history else "concept_seed"
    yield {"type": event_type, "term": term, "brief": brief, "citations": citations}
    yield {"type": "done"}
