"""Synthetic Q/A generator for the evaluation harness.

Generates data/eval/base50.jsonl by:
1. Loading data/parsed/manifest.json
2. Sampling N entries across books (balanced by book_slug)
3. Scrolling the corresponding Qdrant collection for a real chunk
4. Calling OpenAI to generate a question + reference answer from the chunk
5. Writing QARecord entries to the output JSONL file

Wall rule: imports only src.core.*. Does NOT call the chat service.

CLI usage:
    python -m src.services.eval.generator --n 50 --out data/eval/base50.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import uuid
from pathlib import Path
from typing import Any

import openai

from src.core.config import ROOT, settings
from src.core.qdrant_store import client as qdrant_client
from src.services.eval.dataset import QARecord, save

logger = logging.getLogger(__name__)

MANIFEST_PATH = ROOT / "data" / "parsed" / "manifest.json"

_QA_PROMPT_TEMPLATE = """\
Below is an excerpt from a statistics/econometrics textbook. Generate ONE \
specific question that this excerpt directly answers, plus a 2-3 sentence \
reference answer that quotes or paraphrases the excerpt. \
Return JSON: {{"q": "...", "answer": "..."}}

Excerpt:
{chunk_text}"""


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    """Load manifest entries, limited to first 200."""
    with open(path) as f:
        data = json.load(f)
    entries: list[dict[str, Any]] = data.get("entries", data)
    return entries[:200]


def _sample_balanced(
    entries: list[dict[str, Any]],
    n: int,
) -> list[dict[str, Any]]:
    """Sample up to n entries balanced across book_slug values.

    Args:
        entries: Manifest entries to sample from.
        n: Number of entries to select.

    Returns:
        Sampled list with at least 5 different book_slug values (best-effort).
    """
    by_book: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        slug = e.get("book_slug", "")
        if e.get("status") == "success" and e.get("chunk_count", 0) > 0:
            by_book.setdefault(slug, []).append(e)

    books = list(by_book.keys())
    random.shuffle(books)

    selected: list[dict[str, Any]] = []
    # Round-robin across books until we reach n
    round_idx = 0
    while len(selected) < n:
        if not books:
            break
        book = books[round_idx % len(books)]
        pool = by_book[book]
        if pool:
            selected.append(pool.pop(random.randrange(len(pool))))
            if not pool:
                books.remove(book)
                round_idx = round_idx % max(len(books), 1)
                continue
        round_idx += 1

    return selected[:n]


def _fetch_chunk(
    collection: str,
    book_slug: str,
    chapter_id: str,
) -> dict[str, Any] | None:
    """Scroll Qdrant to retrieve one chunk matching the (book_slug, chapter_id) pair.

    Args:
        collection: Qdrant text collection name.
        book_slug: Book slug to filter by.
        chapter_id: Chapter identifier to filter by.

    Returns:
        A dict with keys ``chunk_id``, ``text``, and ``h2_path``, or None if
        no point was found.
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    try:
        results, _ = qdrant_client().scroll(
            collection_name=collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="book_slug",
                        match=MatchValue(value=book_slug),
                    ),
                    FieldCondition(
                        key="chapter_id",
                        match=MatchValue(value=chapter_id),
                    ),
                ]
            ),
            limit=10,
            with_payload=True,
            with_vectors=False,
        )
        if not results:
            return None
        # Pick a random point from the batch
        point = random.choice(results)
        payload = point.payload or {}
        text = payload.get("text") or payload.get("content") or ""
        if not text:
            return None
        return {
            "chunk_id": str(point.id),
            "text": text,
            "h2_path": payload.get("h2_path") or payload.get("section") or "",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Qdrant scroll failed for %s/%s: %s", collection, book_slug, exc)
        return None


def _generate_qa(chunk_text: str) -> dict[str, str] | None:
    """Call OpenAI to produce a question + reference answer for a chunk.

    Args:
        chunk_text: Raw text of the chunk (truncated to 2000 chars).

    Returns:
        Dict with ``q`` and ``answer`` keys, or None on failure.
    """
    prompt = _QA_PROMPT_TEMPLATE.format(chunk_text=chunk_text[:2000])
    oai = openai.OpenAI(api_key=settings.openai_api_key)
    try:
        resp = oai.chat.completions.create(
            model=settings.openai_model_nano,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # Strip markdown fences if present
        raw = raw.strip("```json").strip("```").strip()
        return json.loads(raw)
    except (json.JSONDecodeError, openai.OpenAIError) as exc:
        logger.warning("OpenAI QA generation failed: %s", exc)
        return None


def generate(n: int, out_path: Path) -> None:
    """Generate n Q/A records and write them to out_path.

    Args:
        n: Target number of successful records.
        out_path: Destination JSONL path.
    """
    entries = _load_manifest(MANIFEST_PATH)
    sampled = _sample_balanced(entries, n * 3)  # over-sample to allow for skips
    random.shuffle(sampled)

    records: list[QARecord] = []
    seen_books: set[str] = set()

    for entry in sampled:
        if len(records) >= n:
            break

        book_slug: str = entry["book_slug"]
        chapter_id: str = entry["chapter_id"]
        collection: str = entry.get("qdrant_collection_text", "")

        if not collection:
            logger.info("Skipping %s/%s — no collection in manifest", book_slug, chapter_id)
            continue

        chunk = _fetch_chunk(collection, book_slug, chapter_id)
        if chunk is None:
            logger.info("No chunk found for %s/%s — skipping", book_slug, chapter_id)
            continue

        qa = _generate_qa(chunk["text"])
        if qa is None or not qa.get("q") or not qa.get("answer"):
            logger.info("QA generation failed for %s/%s — skipping", book_slug, chapter_id)
            continue

        record_id = str(uuid.uuid4())[:8]
        rec = QARecord(
            id=record_id,
            q=qa["q"],
            gold_book=book_slug,
            gold_chapter=chapter_id,
            gold_section=chunk["h2_path"],
            gold_chunk_id=chunk["chunk_id"],
            gold_answer=qa["answer"],
            tags=["tutor"],
        )
        records.append(rec)
        seen_books.add(book_slug)
        logger.info(
            "Generated record %d/%d: %s/%s (books so far: %d)",
            len(records), n, book_slug, chapter_id, len(seen_books),
        )

    if len(records) < n:
        logger.warning(
            "Only generated %d/%d records (insufficient unique chunks).", len(records), n
        )

    save(out_path, records)
    logger.info("Wrote %d records to %s", len(records), out_path)
    print(f"Done — {len(records)} records across {len(seen_books)} books → {out_path}")


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Generate synthetic eval Q/A dataset.")
    parser.add_argument("--n", type=int, default=50, help="Number of records to generate.")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "eval" / "base50.jsonl",
        help="Output JSONL path.",
    )
    args = parser.parse_args()
    generate(n=args.n, out_path=args.out)


if __name__ == "__main__":
    main()
