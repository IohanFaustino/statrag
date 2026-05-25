"""One-off preprocessor for Cunningham (Causal Inference: The Mixtape).

Source OCR uses single `#` for every header AND repeats titles across page
breaks. Pipeline regex_pass cannot emit sections from that. This script:

1. Dedupes consecutive duplicate H1s (normalized: alnum + lowercase).
2. Promotes non-chapter H1s to H2.
3. First content occurrence of each chapter title stays as H1; later
   occurrences (e.g. per-chapter "Conclusion" sections) are demoted.

Output: library/_processed/cunningham_fixed.md (yaml `source_path` points here).

Run: .venv/bin/python library/_processed/cunningham_preproc.py
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(
    "/home/iohan/Documents/Converters/Cloud based/Converters/Files/Output/"
    "Introduction/2021_Cunningham/vlm/2021_Cunningham.md"
)
DST = Path(__file__).parent / "cunningham_fixed.md"

CHAPTERS_RAW = [
    "Introduction",
    "Probability and Regression Review",
    "Directed Acyclic Graphs",
    "Potential Outcomes Causal Model",
    "Matching and Subclassification",
    "Regression Discontinuity",
    "Instrumental Variables",
    "Panel Data",
    "Difference-in-Differences",
    "Synthetic Control",
]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main() -> None:
    chapters_norm = {norm(c): c for c in CHAPTERS_RAW}

    lines = SRC.read_text().splitlines()
    out: list[str] = []
    prev_norm: str | None = None
    seen_chapter: set[str] = set()
    dedup = 0
    promoted = 0
    kept = 0

    for ln in lines:
        m = re.match(r"^# (.+?)\s*$", ln)
        if m:
            title = m.group(1).strip()
            n = norm(title)
            if n == prev_norm:
                dedup += 1
                continue
            prev_norm = n
            canonical = chapters_norm.get(n)
            if canonical and canonical not in seen_chapter:
                out.append(f"# {canonical}")
                seen_chapter.add(canonical)
                kept += 1
            else:
                out.append(f"## {title}")
                promoted += 1
        else:
            out.append(ln)

    DST.write_text("\n".join(out) + "\n")
    print(f"src lines: {len(lines)}  dst lines: {len(out)}")
    print(f"chapters kept: {kept}/{len(CHAPTERS_RAW)}  promoted: {promoted}  dedup: {dedup}")
    missing = set(CHAPTERS_RAW) - seen_chapter
    if missing:
        print("MISSING:", missing)


if __name__ == "__main__":
    main()
