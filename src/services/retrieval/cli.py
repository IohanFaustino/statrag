"""Query CLI. Supports text RAG queries and image semantic search.

Examples:
    python -m src.cli "What is the bias-variance tradeoff?"
    python -m src.cli "wage data figure" --search-images
    python -m src.cli "regression" --book islp --show-sources
"""
from __future__ import annotations

import argparse
import sys


def _query_text(question: str, *, book: str | None, show_sources: bool) -> None:
    from src.services.retrieval.chain import build_chain
    chain = build_chain(book_slug=book)
    result = chain.invoke(question)
    print("\n=== ANSWER ===")
    print(result["answer"])
    if show_sources:
        print("\n=== SOURCES ===")
        for i, doc in enumerate(result["sources"], 1):
            meta = doc.metadata
            head = meta.get("h2_path") or meta.get("h1") or ""
            pages = f"pp.{meta.get('page_from','?')}-{meta.get('page_to','?')}"
            preview = doc.page_content[:200].replace("\n", " ")
            print(f"[{i}] {meta.get('book_slug')} / {head} ({pages})")
            print(f"    {preview}...")


def _query_images(query: str, *, book: str | None) -> None:
    from src.services.retrieval.retrievers import search_images
    hits = search_images(query, book_slug=book, k=10)
    if not hits:
        print("No images found.")
        return
    print(f"\n=== IMAGES (top {len(hits)}) ===")
    for i, h in enumerate(hits, 1):
        print(f"[{i}] score={h['score']:.3f}  {h['image_name']}")
        print(f"    book={h['book_name']}  sub={h['subsection']}  page={h.get('page')}")
        print(f"    ref: {h['image_reference'][:120]}")
        print(f"    path: {h['image_path']}\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Hybrid RAG CLI (Qdrant).")
    p.add_argument("question", help="Natural language query.")
    p.add_argument("--book", help="Restrict to a specific book slug (optional).")
    p.add_argument("--show-sources", action="store_true")
    p.add_argument("--search-images", action="store_true",
                   help="Search the image collection instead of text RAG.")
    args = p.parse_args()
    if args.search_images:
        _query_images(args.question, book=args.book)
    else:
        _query_text(args.question, book=args.book, show_sources=args.show_sources)
    return 0


if __name__ == "__main__":
    sys.exit(main())
