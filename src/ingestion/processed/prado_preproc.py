"""Preprocessor for Lopez de Prado (Advances in Financial Machine Learning).

EPUB-converted markdown is largely clean:
    `# CHAPTER N Title`        (chapter)
    `## N.N Title`             (section)
    `### N.N.N Title`          (subsection)
    `#### *N.N.N.N Title*`     (subsubsection, italic-wrapped)

Only fix: H4 headers wrap the numeric body in `*...*`. The regex pass needs
the header text to START with digits to recognize the numeric prefix.
Strip leading/trailing `*` from any header line so the numeric depth match
works at every level.

Lines preserved (no line-number drift).

Output: src/ingestion/processed/prado_fixed.md
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(
    "/home/iohan/Downloads/EPUB/markdown/"
    "Advances in Financial Machine Learning/"
    "Advances in Financial Machine Learning.md"
)
DST = Path(__file__).parent / "prado_fixed.md"

RE_HEADER = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _unwrap_emphasis(text: str) -> str:
    # Strip surrounding **bold** or *italic* markers from a header label.
    # Repeat in case both are present (e.g. "***foo***").
    for _ in range(3):
        m = re.fullmatch(r"\*{1,3}(.+?)\*{1,3}", text)
        if not m:
            break
        text = m.group(1).strip()
    return text


def main() -> None:
    lines = SRC.read_text().splitlines()
    out: list[str] = []
    changed = 0
    for ln in lines:
        m = RE_HEADER.match(ln)
        if m:
            hashes, text = m.group(1), m.group(2).strip()
            cleaned = _unwrap_emphasis(text)
            if cleaned != text:
                changed += 1
            out.append(f"{hashes} {cleaned}")
        else:
            out.append(ln)
    DST.write_text("\n".join(out) + "\n")
    print(f"src lines: {len(lines)}  dst lines: {len(out)}")
    print(f"headers unwrapped: {changed}")


if __name__ == "__main__":
    main()
