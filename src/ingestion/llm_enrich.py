"""Stage C — LLM enrichment of per-section metadata.

For each SectionMetadata: ask the LLM to produce
    - index_extended  : extra keywords (5-15)
    - synopsis        : brief, structured paragraph referencing formulas/figures

Cache: data/parsed/<book>/cache/<section_id>__<provider>__<hash>.json
Idempotent: same content + same provider -> cache hit, no API call.

Prompt uses 1-shot example and strict schema. Defensive parsing coerces
list-typed `synopsis` into a single string (LLMs occasionally drift).
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.core.config import DATA_DIR
from src.ingestion.llm_client import Provider, get_llm
from src.ingestion.schema import SectionMetadata

logger = logging.getLogger(__name__)

CACHE_DIR_NAME = "cache"

SYSTEM = (
    "You output ONLY valid JSON matching this schema strictly:\n"
    '{{"index_extended": list[str], "synopsis": str}}\n\n'
    "Rules:\n"
    "1. `synopsis` MUST be a single string of 1-3 sentences. NEVER an array.\n"
    "2. `index_extended` MUST be a list of 5-15 short, lowercase keywords. "
    "Do not duplicate terms from the existing index.\n"
    "3. Reference formulas, figures and tables by ID when relevant "
    "(e.g., 'eq. (2.7)', 'Figure 2.3', 'Table 1.1').\n"
    "4. No prose outside the JSON. No markdown fences.\n\n"
    "EXAMPLE INPUT:\n"
    "Section: 2.2.3_The_Classification_Setting\n"
    "Formulas: $\\hat{{y}}_0 = \\text{{argmax}}_j P(Y=j|X=x_0)$\n"
    "Images: imgs/img_in_chart_box_2_14.jpg\n"
    "Table refs: TABLE 2.1\n"
    "TEXT: Discussion of Bayes classifier and KNN, decision boundaries, "
    "error rates...\n\n"
    "EXAMPLE OUTPUT:\n"
    '{{"index_extended": ["bayes classifier", "knn", "decision boundary", '
    '"error rate", "majority vote", "classification accuracy", "test error"], '
    '"synopsis": "Section 2.2.3 introduces the classification setting using '
    'the Bayes optimal rule (eq. (2.7)) and the K-nearest neighbors '
    'approximation (Figure 2.14); it contrasts training and test error rates '
    'and motivates flexibility selection."}}'
)

USER = (
    "Book: {book_slug}\nChapter: {chapter_id}\nSection: {h2_path}\n"
    "Formulas detected: {formulas}\n"
    "Images detected: {images}\n"
    "Table refs detected: {table_refs}\n"
    "Existing index_terms (do not duplicate): {existing_index}\n\n"
    "TEXT:\n{text}\n"
)

PROMPT = ChatPromptTemplate.from_messages([("system", SYSTEM), ("user", USER)])


class EnrichOutput(BaseModel):
    index_extended: list[str] = Field(default_factory=list)
    synopsis: str = ""


def _cache_path(book_slug: str, section_id: str, provider: Provider, payload_hash: str) -> Path:
    d = DATA_DIR / "parsed" / book_slug / CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{section_id}__{provider}__{payload_hash}.json"


def _payload_hash(s: SectionMetadata) -> str:
    h = hashlib.md5()
    h.update(s.text.encode("utf-8"))
    h.update("|".join(s.formulas).encode("utf-8"))
    return h.hexdigest()[:12]


def _coerce_synopsis(value) -> str:
    """Defensive: synopsis must be a string. Coerce list -> space-joined string."""
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def enrich_section(
    section: SectionMetadata,
    *,
    provider: Provider = "openai",
    existing_index: list[str] | None = None,
) -> SectionMetadata:
    ph = _payload_hash(section)
    cache_file = _cache_path(section.book_slug, section.section_id, provider, ph)
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
        section.index_extended = data["index_extended"]
        section.synopsis = data["synopsis"]
        logger.debug("Cache hit: %s", cache_file.name)
        return section

    llm = get_llm(provider)
    parser = JsonOutputParser(pydantic_object=EnrichOutput)
    chain = PROMPT | llm | parser
    try:
        result = chain.invoke({
            "book_slug": section.book_slug,
            "chapter_id": section.chapter_id,
            "h2_path": section.h2_path,
            "formulas": section.formulas[:5],
            "images": section.images[:5],
            "table_refs": section.table_refs[:3],
            "existing_index": (existing_index or [])[:30],
            "text": section.text[:12_000],
        })
    except Exception as e:
        logger.warning("LLM enrich failed for %s: %s", section.section_id, e)
        return section

    section.index_extended = list(result.get("index_extended", []))
    section.synopsis = _coerce_synopsis(result.get("synopsis", ""))
    cache_file.write_text(json.dumps({
        "index_extended": section.index_extended,
        "synopsis": section.synopsis,
    }, indent=2))
    return section


def enrich_sections(
    sections: list[SectionMetadata],
    *,
    provider: Provider = "openai",
    existing_index: list[str] | None = None,
) -> list[SectionMetadata]:
    out: list[SectionMetadata] = []
    for i, s in enumerate(sections, 1):
        logger.info("Enriching %d/%d: %s", i, len(sections), s.section_id)
        out.append(enrich_section(s, provider=provider, existing_index=existing_index))
    return out
