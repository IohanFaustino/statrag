"""Preprocessor for Murphy (Probabilistic Machine Learning: An Introduction).

EPUB-converted markdown — no `#` headers. Chapter/section heads encoded as
TOC-back links inside the body:
    [**N Title**](#toc.xhtml#chap-N)            ← chapter
    [**N.N Title**](#toc.xhtml#RSec_N.N)        ← section
    [**N.N.N Title**](#toc.xhtml#RSec_N.N.N)    ← subsection (also handled)

Transform: rewrite those link lines as proper markdown headers.
    `[**1 Introduction**](...)`         → `# Chapter 1 Introduction`
    `[**1.1 Title**](...)`              → `## 1.1 Title`
    `[**1.1.1 Title**](...)`            → `### 1.1.1 Title`

Lines preserved (no line-number drift). Other body content unchanged.

Output: src/ingestion/processed/murphy_fixed.md
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(
    "/home/iohan/Downloads/EPUB/markdown/"
    "Probabilistic Machine Learning _ An Introduction/"
    "Probabilistic Machine Learning _ An Introduction.md"
)
DST = Path(__file__).parent / "murphy_fixed.md"

RE_CHAP = re.compile(r"^\[\*\*(\d+)\s+(.+?)\*\*\]\(.*?\)\s*$")
RE_SEC = re.compile(r"^\[\*\*(\d+(?:\.\d+)+)\s+(.+?)\*\*\]\(.*?\)\s*$")


def main() -> None:
    lines = SRC.read_text().splitlines()
    out: list[str] = []
    chapters = 0
    sections = 0
    for ln in lines:
        m_sec = RE_SEC.match(ln)
        if m_sec:
            num, title = m_sec.group(1), m_sec.group(2).strip()
            depth = num.count(".")
            out.append("#" * (depth + 1) + f" {num} {title}")
            sections += 1
            continue
        m_ch = RE_CHAP.match(ln)
        if m_ch:
            num, title = m_ch.group(1), m_ch.group(2).strip()
            out.append(f"# Chapter {num} {title}")
            chapters += 1
            continue
        out.append(ln)
    DST.write_text("\n".join(out) + "\n")
    print(f"src lines: {len(lines)}  dst lines: {len(out)}")
    print(f"chapters: {chapters}  sections: {sections}")


if __name__ == "__main__":
    main()
