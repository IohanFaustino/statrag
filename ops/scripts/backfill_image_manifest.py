"""Backfill manifest entries for image-only ingests done before
`ingest_images_only.py` started registering them automatically.

For each book that has points in a ``<field>_images`` collection but
no ``chapter_id="images_only"`` manifest entry, write a synthetic
ManifestEntry recording the image count and target collection.

Run once. Idempotent — re-runs skip books that already have an entry.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.ingestion import manifest  # noqa: E402
from src.ingestion.schema import ManifestEntry  # noqa: E402

QDRANT_URL = "http://localhost:6333"
BOOKS_DIR = ROOT / "src" / "ingestion" / "books"


def per_book_counts(coll: str) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    offset = None
    while True:
        body = {"limit": 1000, "with_payload": ["book_slug"]}
        if offset is not None:
            body["offset"] = offset
        req = urllib.request.Request(
            f"{QDRANT_URL}/collections/{coll}/points/scroll",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json"},
        )
        try:
            d = json.load(urllib.request.urlopen(req, timeout=15))
        except Exception:
            return {}
        for p in d.get("result", {}).get("points", []):
            slug = p.get("payload", {}).get("book_slug")
            if slug:
                out[slug] += 1
        offset = d.get("result", {}).get("next_page_offset")
        if not offset:
            break
    return dict(out)


def list_image_collections() -> list[str]:
    try:
        with urllib.request.urlopen(f"{QDRANT_URL}/collections", timeout=5) as r:
            names = [c["name"] for c in json.load(r)["result"]["collections"]]
    except Exception:
        return []
    return [n for n in names if n.endswith("_images")]


def load_book_yaml(slug: str) -> dict | None:
    p = BOOKS_DIR / f"{slug}.yaml"
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text())


def main() -> int:
    existing = {
        e.book_slug for e in manifest.load().entries
        if e.chapter_id == "images_only"
    }
    print(f"Already have {len(existing)} images_only manifest entries")

    registered = 0
    skipped = 0
    for img_coll in list_image_collections():
        for slug, count in per_book_counts(img_coll).items():
            if slug in existing:
                skipped += 1
                continue
            cfg = load_book_yaml(slug)
            if not cfg:
                print(f"  skip {slug}: no yaml")
                continue
            field = cfg.get("field", "")
            text_coll = f"{field}_textbooks"
            source_path = cfg.get("source_path", "")
            # Source hashes are best-effort: if the path resolves we hash
            # it; otherwise a sentinel marker so re-runs don't trip
            # ``should_skip``.
            src = Path(source_path)
            src_hash = manifest.file_hash(src) if src.exists() else "md5:backfilled"
            chap_hash = src_hash
            manifest.register(ManifestEntry(
                book_slug=slug,
                book_name=cfg.get("name", slug),
                chapter_id="images_only",
                source_path=source_path,
                source_hash=src_hash,
                chapter_hash=chap_hash,
                ingested_at=manifest.utcnow(),
                provider="openai",
                chunk_count=0,
                parent_count=0,
                image_count=count,
                qdrant_collection_text=text_coll,
                qdrant_collection_images=img_coll,
                status="success",
            ))
            registered += 1
            print(f"  {slug}: registered {count} → {img_coll}")
            existing.add(slug)

    print(f"\nDone — registered {registered} new entries, skipped {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
