"""Regenerate docs/state.md from data/parsed/manifest.json + ingestion/books/*.yaml.

Run: .venv/bin/python scripts/render_state.py
"""
from __future__ import annotations

import json
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "parsed" / "manifest.json"
BOOKS_DIR = ROOT / "src" / "ingestion" / "books"
OUT = ROOT / "docs" / "state.md"
QDRANT_URL = "http://localhost:6333"


def _qdrant_image_counts_by_book() -> dict[str, int]:
    """Scroll every ``*_images`` collection and return per-book point
    counts. Returns empty dict if Qdrant is unreachable so the renderer
    still works offline."""
    out: dict[str, int] = defaultdict(int)
    try:
        with urllib.request.urlopen(f"{QDRANT_URL}/collections", timeout=2) as r:
            names = [c["name"] for c in json.load(r)["result"]["collections"]]
    except Exception:
        return {}
    for name in names:
        if not name.endswith("_images"):
            continue
        offset = None
        while True:
            body = {"limit": 1000, "with_payload": ["book_slug"]}
            if offset is not None:
                body["offset"] = offset
            req = urllib.request.Request(
                f"{QDRANT_URL}/collections/{name}/points/scroll",
                data=json.dumps(body).encode(),
                headers={"content-type": "application/json"},
            )
            try:
                d = json.load(urllib.request.urlopen(req, timeout=15))
            except Exception:
                break
            for p in d.get("result", {}).get("points", []):
                slug = p.get("payload", {}).get("book_slug")
                if slug:
                    out[slug] += 1
            offset = d.get("result", {}).get("next_page_offset")
            if not offset:
                break
    return dict(out)


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    by_slug = defaultdict(lambda: {"chunks": 0, "chapters": set(), "images": 0,
                                    "text_coll": "", "img_coll": ""})
    for e in manifest.get("entries", []):
        s = e["book_slug"]
        by_slug[s]["chunks"] += e.get("chunk_count", 0)
        by_slug[s]["images"] += e.get("image_count", 0)
        by_slug[s]["chapters"].add(e["chapter_id"])
        by_slug[s]["text_coll"] = e.get("qdrant_collection_text", "")
        by_slug[s]["img_coll"] = e.get("qdrant_collection_images", "")

    # Override image counts with live Qdrant data so image-only ingests
    # (not registered in manifest) are still reflected.
    live_images = _qdrant_image_counts_by_book()
    for slug, n in live_images.items():
        by_slug[slug]["images"] = n

    rows = []
    for yp in sorted(BOOKS_DIR.glob("*.yaml")):
        cfg = yaml.safe_load(yp.read_text())
        slug = cfg["slug"]
        d = by_slug.get(slug, {})
        rows.append({
            "slug": slug,
            "name": cfg["name"],
            "field": cfg.get("field", ""),
            "theme": cfg.get("theme", ""),
            "chapters": len(d.get("chapters") or []),
            "chunks": d.get("chunks", 0),
            "images": d.get("images", 0),
            "text_coll": d.get("text_coll", ""),
            "img_coll": d.get("img_coll", ""),
        })

    lines = [
        "# Ingestion State",
        "",
        f"Regenerated from `data/parsed/manifest.json` + `ingestion/books/*.yaml`.",
        "",
        "Refresh: `.venv/bin/python scripts/render_state.py`",
        "",
        "## Books",
        "",
        "| Slug | Name | Field | Theme | Chapters | Chunks | Images |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['slug']}` | {r['name']} | `{r['field']}` | {r['theme']} | "
            f"{r['chapters']} | {r['chunks']} | {r['images']} |"
        )

    fields = sorted({r["field"] for r in rows if r["field"]})
    lines += ["", "## Collections in use", "",
              "| Field | Text collection | Image collection |",
              "|---|---|---|"]
    for f in fields:
        lines.append(f"| `{f}` | `{f}_textbooks` | `{f}_images` |")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
