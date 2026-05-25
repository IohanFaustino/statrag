"""Preprocessor for Pesaran (Time Series and Panel Data Econometrics, OUP 2015).

EPUB-converted markdown encodes every section header as a markdown link:
    `# [N.N Title](#...)`         -> top-level section under chapter N
    `## [N.N.N Subtitle](#...)`   -> subsection

The pipeline regex pass already understands `# N.N Title` (numeric prefix) as
a section, so the only required transform is to strip the link wrapper.

Notes:
- Some headers have an inline `![image](...)` markdown image in the title
  (e.g. `# [2.6 Covariance matrix of ![image](...)](#...)`). We strip the
  inline image fragment so the header text reads cleanly.
- Some headers have a leading space inside the brackets (`# [ 25.1 Intro]`).
  Tolerated by allowing optional leading whitespace.
- Line numbers preserved: every transformed line is replaced one-for-one;
  no insert/delete. This keeps yaml line ranges valid.

Output: src/ingestion/processed/pesaran_fixed.md
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(
    "/home/iohan/Downloads/EPUB/markdown/"
    "Time Series and Panel Data Econometrics/"
    "Time Series and Panel Data Econometrics.md"
)
DST = Path(__file__).parent / "pesaran_fixed.md"

# Match `# [ N.N(.N...) Title ](url)` capturing depth (#'s) and inner.
RE_LINK_HEADER = re.compile(
    r"^(#{1,6})\s*\[\s*(\d+(?:\.\d+)+)\s+(.+?)\]\([^)]*\)\s*$"
)
# Inline image markdown inside header titles.
RE_INLINE_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
RE_WS = re.compile(r"\s+")


def clean_title(t: str) -> str:
    t = RE_INLINE_IMG.sub("", t)
    t = RE_WS.sub(" ", t).strip()
    return t


def main() -> None:
    lines = SRC.read_text().splitlines()
    out: list[str] = []
    rewritten = 0
    for ln in lines:
        m = RE_LINK_HEADER.match(ln)
        if m:
            hashes, num, title = m.group(1), m.group(2), m.group(3)
            title = clean_title(title)
            out.append(f"{hashes} {num} {title}")
            rewritten += 1
        else:
            out.append(ln)
    DST.write_text("\n".join(out) + "\n")
    print(f"src lines: {len(lines)}  dst lines: {len(out)}")
    print(f"headers rewritten: {rewritten}")


if __name__ == "__main__":
    main()
