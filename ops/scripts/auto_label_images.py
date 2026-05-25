"""Auto-fill `label_include` and `label_aspect` columns of the image
eval CSV using GPT-4o (vision) as an oracle.

Treat its output as a *baseline*, not ground-truth. Human review can
override individual rows by editing the CSV after this runs.

Reads:  data/eval/image_label_set.csv  (rows from build_image_label_set.py)
Writes: same path in-place (after backing up to *.bak)
Cost:   ~32 vision calls @ gpt-4o-mini ≈ $0.05.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import openai as _openai  # noqa: E402
from src.core.config import settings  # noqa: E402


SYSTEM_PROMPT = """\
You are an image pertinence oracle for an AI tutor over statistics /
econometrics / ML textbooks. Look at the image and decide:
(1) should it be included in an answer to the given query?
(2) which DeepTutorAnswer aspect does it best illustrate?

Aspect choices: tldr, definition, formal_statement, intuition,
examples, trade_offs, further_reading.

Be strict: decorative photos, chapter front-matter, code listings,
unreadable scans, or off-topic figures should be excluded (include=0).
Include only when the image clearly illustrates a concept the query is
about.

Return ONLY a JSON object:
  {"include": 0|1, "aspect": "<aspect>"|null, "reason": "<= 20 words"}
"""


_PATH_REWRITES: list[tuple[str, str]] = [
    # Qdrant ingestion stored absolute paths pointing at a tree that has
    # since been relocated under /Documents/Converters/. Remap on the fly.
    ("/home/iohan/Documents/Books/", "/home/iohan/Documents/Converters/Books/"),
]


def _path_from_url(url: str) -> Path | None:
    """`/api/figures?path=%2Fhome%2F...jpg` -> Path(/home/.../jpg).

    Applies known path rewrites so stored paths still resolve after the
    source tree moved.
    """
    if not url:
        return None
    marker = "path="
    i = url.find(marker)
    if i < 0:
        return None
    p = unquote(url[i + len(marker):])
    for old, new in _PATH_REWRITES:
        if p.startswith(old):
            p = new + p[len(old):]
            break
    return Path(p)


def _read_image_b64(path: Path) -> tuple[str, str] | None:
    """Return (mime, b64) or None if file unreadable."""
    if not path.exists():
        return None
    suffix = path.suffix.lower().lstrip(".")
    mime = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    }.get(suffix, "image/jpeg")
    data = path.read_bytes()
    if len(data) > 8 * 1024 * 1024:  # 8 MB hard cap
        return None
    return mime, base64.b64encode(data).decode()


def label_row(client: _openai.OpenAI, row: dict[str, str], model: str) -> dict:
    query = row.get("query", "")
    caption = (row.get("caption") or "").strip()
    url = row.get("image_url", "")
    fp = _path_from_url(url)
    img = _read_image_b64(fp) if fp else None
    if img is None:
        return {"include": 0, "aspect": None,
                "reason": "image file missing or too large"}
    mime, b64 = img
    user_content = [
        {"type": "text", "text": (
            f"<query>{query}</query>\n"
            f"<caption>{caption[:600]}</caption>"
        )},
        {"type": "image_url",
         "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
                max_completion_tokens=120,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
            return {
                "include": 1 if int(data.get("include", 0)) else 0,
                "aspect": data.get("aspect") or None,
                "reason": str(data.get("reason", ""))[:200],
            }
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            msg = str(exc).lower()
            if "rate" in msg or "429" in msg or "timeout" in msg:
                time.sleep(min(2 ** attempt * 4, 30))
                continue
            break
    return {"include": 0, "aspect": None,
            "reason": f"oracle error: {last_err}"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/eval/image_label_set.csv")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--limit", type=int, default=0,
                    help="0 = all rows; otherwise label only first N")
    ap.add_argument("--overwrite", action="store_true",
                    help="re-label rows that already have label_include")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")
    backup = csv_path.with_suffix(csv_path.suffix + ".bak")
    shutil.copy2(csv_path, backup)
    print(f"backup -> {backup}")

    with csv_path.open() as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        sys.exit("CSV empty")
    fieldnames = list(rows[0].keys())

    client = _openai.OpenAI(api_key=settings.openai_api_key)

    targets = rows if args.overwrite else [
        r for r in rows if not (r.get("label_include") or "").strip()
    ]
    if args.limit:
        targets = targets[: args.limit]
    print(f"labelling {len(targets)} rows with {args.model}...")

    t0 = time.monotonic()
    for i, row in enumerate(targets, 1):
        out = label_row(client, row, args.model)
        row["label_include"] = str(out["include"])
        row["label_aspect"] = out["aspect"] or ""
        existing_notes = row.get("notes", "") or ""
        tag = f"auto({args.model}): {out['reason']}"
        row["notes"] = (existing_notes + " | " + tag).strip(" |") if existing_notes else tag
        print(f"  [{i}/{len(targets)}] include={out['include']} "
              f"aspect={out['aspect']} :: {out['reason'][:80]}")

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"done in {time.monotonic() - t0:.1f}s")


if __name__ == "__main__":
    main()
