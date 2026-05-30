"""Generic preprocessor for Packt kobo/EPUB-HTML markdown exports.

Several GenAI/LLM books were OCR'd into Pandoc markdown where every text
fragment is a `[text]{#anchor .koboSpan ...}` span, page numbers live in
`.pagebreak` spans, and headers carry semantic classes instead of markdown
levels. `regex_pass` cannot parse that. This script runs the source through
``pandoc`` with ``kobo_filter.lua`` (unwrap spans, emit `<!-- page N -->`,
remap header levels), then post-processes:

  * merge a lone ``# N`` chapter-number heading with the following
    ``# Title`` -> ``# N Title`` (the chapter backbone regex_pass keys on);
  * collapse runs of blank lines.

Output: ``src/ingestion/processed/<slug>_fixed.md`` (point the book yaml
``source_path`` here). Run:

    .venv/bin/python -m src.ingestion.processed.kobo_preproc \
        --src "/abs/path/to/input.md" --slug neo4j_llm
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILTER = HERE / "kobo_filter.lua"

# a lone chapter-number heading: "# 12" (digits only, optional trailing space)
RE_NUM_ONLY_H1 = re.compile(r"^#\s+(\d+)\s*$")
RE_H1 = re.compile(r"^#\s+(.+?)\s*$")
RE_BLANKS = re.compile(r"\n{3,}")
RE_FENCE = re.compile(r"^\s*(```+|~~~+)")
# a stripped line that looks like a markdown ATX header: hashes + space + text
RE_ATX_STRIPPED = re.compile(r"^(#{1,6})\s+\S")


def neutralize_code_comments(text: str) -> tuple[str, int]:
    """Stop code-block ``# comment`` lines being read as headers.

    ``regex_pass`` ``line.strip()``s each line before header-matching and does
    NOT track code blocks, so a Python/bash ``# comment`` inside a code block is
    mis-parsed as an H1 (the line is dropped from the body and ``h1`` gets
    relabelled). A *real* header emitted by this preprocessor is always at
    column 0; a code comment is either inside a ``` fence or indented (>=1
    leading space). For both cases we delete the space after the leading hashes
    (``# Foo`` -> ``#Foo``, preserving indentation): still a valid code comment,
    no longer matches ``regex_pass``'s ``RE_HEADER`` (``#{1,6}\\s+``).
    """
    out: list[str] = []
    in_fence = False
    fixed = 0
    for ln in text.splitlines():
        if RE_FENCE.match(ln):
            in_fence = not in_fence
            out.append(ln)
            continue
        stripped = ln.lstrip()
        if RE_ATX_STRIPPED.match(stripped):
            indented = ln != stripped  # had leading whitespace
            if in_fence or indented:
                lead = ln[: len(ln) - len(stripped)]
                out.append(lead + re.sub(r"^(#{1,6})\s+", r"\1", stripped))
                fixed += 1
                continue
        out.append(ln)
    return "\n".join(out), fixed


def run_pandoc(src: Path) -> str:
    """Convert the kobo markdown to clean gfm via the unwrap filter."""
    proc = subprocess.run(
        [
            "pandoc", "-f", "markdown", "-t", "gfm",
            f"--lua-filter={FILTER}", "--wrap=none", str(src),
        ],
        capture_output=True, text=True, check=True,
    )
    return proc.stdout


def merge_chapter_headings(text: str) -> tuple[str, int]:
    """Collapse a lone ``# N`` chapter-number heading into the following
    ``# Title`` heading, emitting a clean ``# Title`` (the number is dropped so
    it does not leak into the section ``h1``). The lone-number + title pattern
    is the chapter detector; one output line replaces the two input headings,
    so downstream line positions are unchanged versus a plain merge.
    """
    lines = text.splitlines()
    out: list[str] = []
    merged = 0
    i = 0
    while i < len(lines):
        m = RE_NUM_ONLY_H1.match(lines[i])
        if m:
            # look ahead past blank lines for the next H1 (the title)
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if j < len(lines):
                t = RE_H1.match(lines[j])
                if t:
                    out.append(f"# {t.group(1)}")
                    merged += 1
                    i = j + 1
                    continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), merged


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="absolute path to kobo input.md")
    ap.add_argument("--slug", required=True, help="book slug (output filename)")
    args = ap.parse_args()

    src = Path(args.src)
    dst = HERE / f"{args.slug}_fixed.md"

    gfm = run_pandoc(src)
    merged_text, n_merged = merge_chapter_headings(gfm)
    merged_text, n_cc = neutralize_code_comments(merged_text)
    merged_text = RE_BLANKS.sub("\n\n", merged_text).strip() + "\n"
    dst.write_text(merged_text, encoding="utf-8")

    n_pages = merged_text.count("<!-- page ")
    n_h1 = sum(1 for ln in merged_text.splitlines() if ln.startswith("# "))
    n_h2 = sum(1 for ln in merged_text.splitlines() if ln.startswith("## "))
    print(f"src: {src}")
    print(f"dst: {dst}  ({len(merged_text.splitlines())} lines)")
    print(f"chapter headings merged: {n_merged}   code-comment headers neutralized: {n_cc}")
    print(f"page markers: {n_pages}   H1: {n_h1}   H2: {n_h2}")


if __name__ == "__main__":
    main()
