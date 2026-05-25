"""Coverage check + targeted re-query (CRAG-lite) for the tutor.

After retrieval, grade the selected sources against the query planner's
``facets`` (the things the answer must cover). For any unsupported facet, run a
targeted retrieval to fill the gap. Best-effort: any failure → no change.

Example it fixes: "What is the bias-variance tradeoff?" where the variance
formula was never retrieved — the ``variance formula`` facet is graded missing,
re-queried, and merged in before drafting.
"""
from __future__ import annotations

import asyncio
import json
import logging

import openai as _openai

from src.core.config import settings
from src.services.chat.prompts.deep_tutor import COVERAGE_PROMPT, format_source_bundle
from src.services.chat.retrieval import hybrid_search
from src.services.chat.schemas import Source
from src.services.chat._fences import strip_fences

logger = logging.getLogger(__name__)

# Coverage check ON by default; disable with TUTOR_COVERAGE_CHECK=0.
import os
COVERAGE_ON = os.environ.get("TUTOR_COVERAGE_CHECK", "1") == "1"


def _client(model_id: str | None = None) -> _openai.AsyncOpenAI:
    from src.services.chat.llm.router import aclient_for  # noqa: PLC0415
    return aclient_for(model_id)


async def assess_coverage(
    query: str, facets: list[str], sources: list[Source], *, model: str | None = None
) -> list[str]:
    """Return the subset of *facets* NOT supported by *sources*. Best-effort:
    ``[]`` on empty facets/sources or any error."""
    facets = [f for f in (facets or []) if f.strip()]
    if not facets or not sources:
        return []
    user = (
        f"<question>\n{query}\n</question>\n\n"
        f"facets: {json.dumps(facets)}\n\n"
        f"{format_source_bundle(sources)}\n\n"
        f"Return the missing-facets JSON now."
    )
    try:
        chosen = model or settings.openai_model_nano
        resp = await _client(chosen).chat.completions.create(
            model=chosen,
            messages=[
                {"role": "system", "content": COVERAGE_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_completion_tokens=200,
        )
        parsed = json.loads(strip_fences(resp.choices[0].message.content or "{}"))
        missing = [str(x).strip() for x in (parsed.get("missing") or []) if str(x).strip()]
        # Only return facets we actually asked about.
        facet_set = set(facets)
        return [m for m in missing if m in facet_set]
    except Exception:  # noqa: BLE001
        logger.exception("assess_coverage failed; assuming covered")
        return []


async def fill_missing_facets(
    missing: list[str],
    book_slugs: list[str] | None,
    pool: int,
    seen_ids: set[str],
) -> list[Source]:
    """One targeted retrieval per missing facet; dedup against *seen_ids*."""
    if not missing:
        return []
    results = await asyncio.gather(
        *(asyncio.to_thread(hybrid_search, m, book_slugs=book_slugs, top_k=pool, rerank=False)
          for m in missing),
        return_exceptions=True,
    )
    out: list[Source] = []
    for r in results:
        if isinstance(r, BaseException):
            continue
        for src in r[0]:
            if src.chunkId and src.chunkId not in seen_ids:
                seen_ids.add(src.chunkId)
                out.append(src)
    return out
