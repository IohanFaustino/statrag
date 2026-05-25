"""Stage D — assemble one Document per section (chunked at 8K tokens).

Single-tier chunking. NO parent/child split.
    section <= TARGET_TOKENS  -> 1 chunk
    section >  TARGET_TOKENS  -> N chunks of TARGET_TOKENS with OVERLAP_TOKENS

Token counter: tiktoken `cl100k_base` (matches text-embedding-3-large /
gpt-4* family). Embedding API caps at 8191 tokens; TARGET_TOKENS=8000 leaves
a safe margin.

Monitoring: returns a `BuildStats` dict with chunk count, token min/max/mean,
oversize_count (should be 0), section_to_chunks ratio.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

import tiktoken
from langchain_core.documents import Document

from src.core.config import settings
from src.ingestion.schema import BookMetadata, SectionMetadata

logger = logging.getLogger(__name__)

_ENC = tiktoken.get_encoding("cl100k_base")
TARGET_TOKENS = 8000
OVERLAP_TOKENS = 200
HARD_MAX_TOKENS = 8190  # safety cap below the 8191 embedding limit


def count_tokens(text: str) -> int:
    # disallowed_special=() lets source text containing literal tokens like
    # `<|endoftext|>` (e.g. NLP textbook examples) encode as normal characters.
    return len(_ENC.encode(text, disallowed_special=()))


def _split_by_tokens(text: str, target: int = TARGET_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[str]:
    """Token-window split. Returns 1 chunk if input <= target."""
    tokens = _ENC.encode(text, disallowed_special=())
    if len(tokens) <= target:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + target, len(tokens))
        chunks.append(_ENC.decode(tokens[start:end]))
        if end >= len(tokens):
            break
        start = end - overlap
    return chunks


def _chunk_id(prefix: str, text: str) -> str:
    return f"{prefix}_{hashlib.md5(text.encode('utf-8')).hexdigest()[:16]}"


def _flat_meta(s: SectionMetadata, book: BookMetadata) -> dict:
    return {
        "book": s.book_slug,
        "book_slug": s.book_slug,
        "book_name": book.name,
        "theme": book.theme or "",
        "authors": ", ".join(book.authors),
        "chapter_id": s.chapter_id,
        "section_id": s.section_id,
        "h1": s.h1 or "",
        "h2_path": s.h2_path,
        "page_from": s.page_from if s.page_from is not None else -1,
        "page_to": s.page_to if s.page_to is not None else -1,
        "has_formula": bool(s.formulas),
        "has_image": bool(s.images),
        "has_table": bool(s.tables_html),
        "n_formulas": len(s.formulas),
        "synopsis": (s.synopsis or "")[:500],
        "index_extended": ",".join(s.index_extended[:20]),
    }


@dataclass
class BuildStats:
    n_sections: int = 0
    n_chunks: int = 0
    n_oversize: int = 0          # chunks above HARD_MAX_TOKENS (must be 0)
    split_sections: int = 0      # sections that needed >1 chunk
    token_min: int = 0
    token_max: int = 0
    token_mean: float = 0.0
    token_histogram: dict[str, int] = field(default_factory=dict)
    per_section: list[dict] = field(default_factory=list)


def build(sections: list[SectionMetadata], book: BookMetadata) -> tuple[list[Document], list[str], BuildStats]:
    """Build one or more Documents per section with token-aware chunking."""
    docs: list[Document] = []
    ids: list[str] = []
    token_counts: list[int] = []
    stats = BuildStats(n_sections=len(sections))

    for s in sections:
        meta = _flat_meta(s, book)
        pieces = _split_by_tokens(s.text, TARGET_TOKENS, OVERLAP_TOKENS)
        if len(pieces) > 1:
            stats.split_sections += 1

        for idx, piece in enumerate(pieces):
            n_tok = count_tokens(piece)
            token_counts.append(n_tok)
            if n_tok > HARD_MAX_TOKENS:
                stats.n_oversize += 1
                logger.error(
                    "Chunk %s[%d] exceeds %d tokens (%d) — embedding will truncate!",
                    s.section_id, idx, HARD_MAX_TOKENS, n_tok,
                )
            cid = _chunk_id(f"{s.section_id}_{idx}", piece)
            ids.append(cid)
            piece_meta = {**meta, "chunk_index": idx, "n_chunks_in_section": len(pieces),
                          "token_count": n_tok}
            docs.append(Document(page_content=piece, metadata=piece_meta))

        stats.per_section.append({
            "section_id": s.section_id,
            "h2_path": s.h2_path,
            "n_chunks": len(pieces),
            "tokens": [count_tokens(p) for p in pieces],
            "char_count": s.char_count,
        })

    # dedupe by id (idempotent re-ingest)
    seen: set[str] = set()
    uniq_docs: list[Document] = []
    uniq_ids: list[str] = []
    for d, i in zip(docs, ids):
        if i in seen:
            continue
        seen.add(i)
        uniq_docs.append(d)
        uniq_ids.append(i)

    stats.n_chunks = len(uniq_docs)
    if token_counts:
        stats.token_min = min(token_counts)
        stats.token_max = max(token_counts)
        stats.token_mean = sum(token_counts) / len(token_counts)
        buckets = {"<1k": 0, "1k-2k": 0, "2k-4k": 0, "4k-6k": 0, "6k-8k": 0, ">8k": 0}
        for n in token_counts:
            if n < 1000: buckets["<1k"] += 1
            elif n < 2000: buckets["1k-2k"] += 1
            elif n < 4000: buckets["2k-4k"] += 1
            elif n < 6000: buckets["4k-6k"] += 1
            elif n <= 8000: buckets["6k-8k"] += 1
            else: buckets[">8k"] += 1
        stats.token_histogram = buckets

    logger.info(
        "Build stats: sections=%d chunks=%d split=%d oversize=%d "
        "tokens(min/mean/max)=%d/%.0f/%d  hist=%s",
        stats.n_sections, stats.n_chunks, stats.split_sections,
        stats.n_oversize, stats.token_min, stats.token_mean, stats.token_max,
        stats.token_histogram,
    )
    return uniq_docs, uniq_ids, stats


# --- legacy shims (no-op; old retriever signature) ---------------------------


def load_parents(_book_slug: str | None = None) -> dict:
    """Compatibility stub — parent doc pattern removed. Returns empty dict."""
    return {}


def save_parents(*_args, **_kwargs) -> None:
    """No-op. Section-level chunks make parents unnecessary."""
    return None
