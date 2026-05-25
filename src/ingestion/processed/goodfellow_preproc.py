"""Preprocessor for Goodfellow et al. (Deep Learning, MIT Press 2016).

EPUB-converted markdown — no `#` headers. The TOC (lines <~530) holds
`part00NN.xhtml` links. The body uses `part0005.xhtml#aXXX` links (part0005
is the contents page), which is how we distinguish body heads from TOC.

Body chapter heads look like (two lines):
    [N](#part0005.xhtml#aXXX)
    <blank>
    [Title](#part0005.xhtml#aXXX)

Body section heads look like one line:
    [N.N     Section Title](#part0005.xhtml#aXXX)
    [N.N.N   Subsection Title](#part0005.xhtml#aXXX)

Body part heads look like:
    [I](#part0005.xhtml#aXXX)
    <blank>
    [Part Title](#part0005.xhtml#aXXX)

Transform: emit headers on the same lines as the link, preserving line
numbers. For two-line chapter/part heads, the number line becomes blank
and the title line becomes the header carrying the chapter number.

Output: src/ingestion/processed/goodfellow_fixed.md
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(
    "/home/iohan/Downloads/EPUB/markdown/Deep Learning/Deep Learning.md"
)
DST = Path(__file__).parent / "goodfellow_fixed.md"

# Body links target part0005.xhtml (the contents page back-link).
BODY = r"#part0005\.xhtml#"

RE_CHAP_NUM = re.compile(rf"^\[(\d+)\]\({BODY}[A-Za-z0-9]+\)\s*$")
RE_PART_NUM = re.compile(rf"^\[([IVX]+)\]\({BODY}[A-Za-z0-9]+\)\s*$")
RE_TITLE = re.compile(rf"^\[(.+?)\]\({BODY}[A-Za-z0-9]+\)\s*$")
RE_SEC = re.compile(
    rf"^\[(\d+(?:\.\d+)+)\s+(.+?)\]\({BODY}[A-Za-z0-9]+\)\s*$"
)


def main() -> None:
    lines = SRC.read_text().splitlines()
    out: list[str] = list(lines)  # copy; we'll rewrite in place
    n_chap = n_part = n_sec = 0
    pending: tuple[str, str, int] | None = None  # (kind, number, line_idx)

    for i, ln in enumerate(lines):
        # Sections first (single-line)
        m_sec = RE_SEC.match(ln)
        if m_sec:
            num, title = m_sec.group(1), m_sec.group(2).strip()
            depth = num.count(".")
            out[i] = "#" * (depth + 1) + f" {num} {title}"
            n_sec += 1
            pending = None
            continue
        m_ch = RE_CHAP_NUM.match(ln)
        if m_ch:
            pending = ("chap", m_ch.group(1), i)
            continue
        m_pt = RE_PART_NUM.match(ln)
        if m_pt:
            pending = ("part", m_pt.group(1), i)
            continue
        if pending is not None:
            # skip blank lines while looking for the title
            if ln.strip() == "":
                continue
            m_t = RE_TITLE.match(ln)
            if m_t:
                kind, num, num_idx = pending
                title = m_t.group(1).strip()
                if kind == "chap":
                    out[num_idx] = ""  # blank out number-only line
                    out[i] = f"# Chapter {num} {title}"
                    n_chap += 1
                else:  # part
                    out[num_idx] = ""
                    out[i] = f"# Part {num} {title}"
                    n_part += 1
            pending = None

    DST.write_text("\n".join(out) + "\n")
    print(f"src lines: {len(lines)}  dst lines: {len(out)}")
    print(f"chapters: {n_chap}  parts: {n_part}  sections: {n_sec}")


if __name__ == "__main__":
    main()
