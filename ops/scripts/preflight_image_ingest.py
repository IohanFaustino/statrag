"""Preflight audit for image-only ingestion from new VLM output.

Read-only. Maps each book slug to its vlm/<book>.md (if it exists),
counts on-disk images, counts existing points in the corresponding
<field>_images Qdrant collection. Writes a single report JSON to
``/tmp/ingest_audit.json`` and prints a human-friendly summary.

Usage:
    python ops/scripts/preflight_image_ingest.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BOOKS_DIR = ROOT / "src" / "ingestion" / "books"
VLM_ROOT = Path("/home/iohan/Documents/Converters/Cloud based/Converters/Files/Output")
QDRANT_URL = "http://localhost:6333"

# Map yaml `field` value → existing Qdrant text collection (for sanity).
EXISTING_TEXT = {
    "causal_inference": "causal_inference_textbooks",
    "econometrics":     "econometrics_textbooks",
    "introduction":     "introduction_textbooks",
    "math":             "math_textbooks",
    "ml_dp":            "ml_dp_textbooks",
    "risk":             "risk_textbooks",
}

# Heuristic vlm-dir name → slug; for the 17 known books we can also match
# yaml slug substrings against the directory name.
_VLM_HINTS = {
    "Morgan_etal":              "morgan",
    "Pearl_Glaymour_Jewell":    "pearl",
    "Peters":                   "peters",     # 2017 Peters/Janzing/Schölkopf
    "Hernán_Robins":            "hernan",
    "Gujarati_Porter":          "gujarati",
    "Baltagi":                  "baltagi",
    "Hansen":                   "hansen",
    "Atwan":                    "atwan",
    "Peck_Olsen_Devore":        "peck",
    "Wooldridge":               "wooldridge",
    "Neal":                     "neal",
    "Cunningham":               "cunningham",
    "Moss":                     "moss",
    "MacKay":                   "mackay",
    "Lis_Rosser":               "lis_rosser",
    "Chollet_Watson":           "chollet",
    "McNeil_Frey_Embrechts":    "mcneil",
}


def find_vlm_for_slug(slug: str) -> Path | None:
    if not VLM_ROOT.exists():
        return None
    for vlm_dir in VLM_ROOT.rglob("vlm"):
        if not vlm_dir.is_dir():
            continue
        # parent dir name like "2022_Hansen"
        parent_name = vlm_dir.parent.name
        for hint, hint_slug in _VLM_HINTS.items():
            if hint in parent_name and hint_slug == slug:
                # find the <book>.md inside vlm/
                mds = list(vlm_dir.glob("*.md"))
                return mds[0] if mds else None
    return None


def count_images_on_disk(vlm_md: Path) -> int:
    images_dir = vlm_md.parent / "images"
    if not images_dir.exists():
        return 0
    return sum(1 for _ in images_dir.glob("*.jpg")) + sum(1 for _ in images_dir.glob("*.png"))


def count_qdrant_points(collection: str) -> int | None:
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen(f"{QDRANT_URL}/collections/{collection}", timeout=2) as r:
            data = json.load(r)
        return data.get("result", {}).get("points_count")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def count_md_image_refs(md_path: Path) -> int:
    if not md_path.exists():
        return 0
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    return len(re.findall(r"!\[\]\(images/[^)]+\)", text))


def main() -> int:
    rows: list[dict] = []
    for yaml_path in sorted(BOOKS_DIR.glob("*.yaml")):
        slug = yaml_path.stem
        cfg = yaml.safe_load(yaml_path.read_text())
        field = cfg.get("field", "?")
        text_coll = EXISTING_TEXT.get(field, f"{field}_textbooks")
        img_coll = f"{field}_images"
        vlm_md = find_vlm_for_slug(slug)
        disk_imgs = count_images_on_disk(vlm_md) if vlm_md else 0
        md_refs = count_md_image_refs(vlm_md) if vlm_md else 0
        existing_pts = count_qdrant_points(img_coll)
        rows.append({
            "slug": slug,
            "field": field,
            "text_collection": text_coll,
            "image_collection": img_coll,
            "vlm_md": str(vlm_md) if vlm_md else None,
            "disk_image_files": disk_imgs,
            "md_image_refs": md_refs,
            "existing_image_points": existing_pts,
            "status": (
                "ready" if vlm_md and md_refs > 0 else
                "missing-vlm" if not vlm_md else
                "no-image-refs"
            ),
        })

    out = ROOT / "data" / "parsed" / "_ingest_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2))

    print(f"\nAudit written → {out}\n")
    print(f"{'slug':<14}{'field':<18}{'vlm?':<6}{'disk_imgs':<11}{'md_refs':<9}{'existing_pts':<14}{'status'}")
    print("-" * 90)
    for r in rows:
        print(
            f"{r['slug']:<14}"
            f"{r['field']:<18}"
            f"{('yes' if r['vlm_md'] else 'no'):<6}"
            f"{r['disk_image_files']:<11}"
            f"{r['md_image_refs']:<9}"
            f"{str(r['existing_image_points']):<14}"
            f"{r['status']}"
        )

    ready = [r for r in rows if r["status"] == "ready"]
    missing = [r for r in rows if r["status"] != "ready"]
    print(f"\n{len(ready)} ready to ingest · {len(missing)} skipped")
    print("Ready slugs:", " ".join(r["slug"] for r in ready))
    return 0


if __name__ == "__main__":
    sys.exit(main())
