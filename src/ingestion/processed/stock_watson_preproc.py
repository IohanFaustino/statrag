"""Preprocessor for Stock & Watson (MyLab Intro to Econometrics 4e, EPUB-MD).

EPUB-converted markdown wraps every header in inline `<span>` tags.
Stripping all HTML tags from header lines exposes clean `# Chapter N Title`
and `# N.N Title` patterns the pipeline already handles.

Also strips any kobo span IDs from body lines (keeps text, drops markup).

Output: src/ingestion/processed/stock_watson_fixed.md
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(
    "/home/iohan/Downloads/EPUB/markdown/"
    "Introduction/MyLab Economics -- for Introduction to Econometrics, 4_e/"
    "MyLab Economics -- for Introduction to Econometrics, 4_e.md"
)
DST = Path(__file__).parent / "stock_watson_fixed.md"

RE_TAG = re.compile(r"<[^>]+>")
RE_WS = re.compile(r"\s+")


def strip_html(s: str) -> str:
    s = RE_TAG.sub("", s)
    s = s.replace("\\#", "#").replace("\\_", "_")
    s = RE_WS.sub(" ", s).strip()
    return s


def main() -> None:
    lines = SRC.read_text().splitlines()
    out: list[str] = []
    stripped_headers = 0
    stripped_body = 0
    for ln in lines:
        if ln.startswith("# "):
            cleaned = strip_html(ln[2:])
            if cleaned:
                out.append(f"# {cleaned}")
                stripped_headers += 1
            else:
                out.append("")
        elif "<span" in ln or "<div" in ln or "</span" in ln or "</div" in ln:
            cleaned = strip_html(ln)
            out.append(cleaned)
            stripped_body += 1
        else:
            out.append(ln)
    DST.write_text("\n".join(out) + "\n")
    print(f"src lines: {len(lines)}  dst lines: {len(out)}")
    print(f"headers cleaned: {stripped_headers}  body lines cleaned: {stripped_body}")


if __name__ == "__main__":
    main()
