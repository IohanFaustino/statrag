"""Generate a 30-row image-pertinence label CSV for quality evaluation.

For each of a small list of seed queries, runs ``fetch_image_candidates``
against the live Qdrant image collections and writes one CSV row per
candidate.  The CSV is then hand-labelled (``label_include``,
``label_aspect`` columns) by the user; the nightly
``pytest -m quality_images`` lane compares the judge's verdicts against
those labels and reports precision / recall / F1.

Usage::

    .venv/bin/python ops/scripts/build_image_label_set.py \
        --out data/eval/image_label_set.csv \
        --per-query 4

Chinese-wall: imports only from ``src.services.chat.*``.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.services.chat.retrievers.image_density import fetch_image_candidates  # noqa: E402


SEED_QUERIES: list[str] = [
    "What is the bias-variance tradeoff?",
    "How does gradient descent converge?",
    "What is a confidence interval?",
    "Explain the transformer attention mechanism.",
    "What is a confounding variable?",
    "How does k-nearest neighbours work?",
    "What is a regression discontinuity design?",
    "What is the bootstrap method?",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-query", type=int, default=4)
    ap.add_argument("--queries", nargs="*", default=SEED_QUERIES)
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    for query in args.queries:
        cands = fetch_image_candidates(query, [], book_slugs=None,
                                       pool=args.per_query)
        for c in cands:
            f = c.figure
            rows.append({
                "query": query,
                "image_ref": f.ref,
                "book": f.book,
                "chapter": f.chapter,
                "caption": (f.caption or "").replace("\n", " ").strip()[:500],
                "image_url": f.chart or "",
                "co_located": "1" if c.co_located else "0",
                "similarity": f"{c.similarity:.3f}",
                # Empty columns for the human reviewer to fill in.
                "label_include": "",
                "label_aspect": "",
                "notes": "",
            })

    fieldnames = [
        "query", "image_ref", "book", "chapter", "caption", "image_url",
        "co_located", "similarity", "label_include", "label_aspect", "notes",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_path}")
    print("Fill 'label_include' (0/1) and 'label_aspect' "
          "(tldr|definition|formal_statement|intuition|examples|trade_offs|further_reading)")


if __name__ == "__main__":
    main()
