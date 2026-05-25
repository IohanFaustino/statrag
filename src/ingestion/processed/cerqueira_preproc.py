"""One-off preprocessor for Cerqueira & Roque (Deep Learning for Time Series Cookbook).

Packt cookbook EPUB->MD: flat OCR uses single `#` for every header — chapter
numbers (`# 1`), chapter titles (`# Getting Started with Time Series`),
section names (`# Visualizing a time series`), and recipe subsections
(`## Getting ready`, `## How to do it…`).

If left as-is, the pipeline regex_pass would treat every `#` as H1,
overwriting current_h1 → effectively zero proper sections. Same template
as Atwan: demote every `# X` to `## X`. The yaml-supplied chapter_title
becomes H1; each former H1 becomes a section. Dedupe consecutive duplicates
(page-bleed safety) WITHOUT removing lines (replace with empty so line
numbers stay aligned — yaml line ranges remain valid).

Output: src/ingestion/processed/cerqueira_fixed.md
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(
    "/home/iohan/Downloads/EPUB/markdown/"
    "Deep Learning for Time Series Cookbook_ Use PyTorch and -- "
    "Vitor Cerqueira & Luís Roque -- 2024 -- Packt Publishing Pvt Ltd -- "
    "36798e5b9c4126281a1cf569f366b397 -- Anna’s Archive/"
    "Deep Learning for Time Series Cookbook_ Use PyTorch and -- "
    "Vitor Cerqueira & Luís Roque -- 2024 -- Packt Publishing Pvt Ltd -- "
    "36798e5b9c4126281a1cf569f366b397 -- Anna’s Archive.md"
)
DST = Path(__file__).parent / "cerqueira_fixed.md"

RE_H1 = re.compile(r"^# (.+?)\s*$")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main() -> None:
    lines = SRC.read_text().splitlines()
    out: list[str] = []
    prev_norm: str | None = None
    promoted = 0
    dedup = 0

    for ln in lines:
        m = RE_H1.match(ln)
        if m:
            title = m.group(1).strip()
            n = norm(title)
            if n == prev_norm:
                out.append("")  # keep line count
                dedup += 1
            else:
                out.append(f"## {title}")
                prev_norm = n
                promoted += 1
        else:
            out.append(ln)

    DST.write_text("\n".join(out) + "\n")
    print(f"src lines: {len(lines)}  dst lines: {len(out)}")
    print(f"H1->H2 promoted: {promoted}  dedup (blanked): {dedup}")


if __name__ == "__main__":
    main()
