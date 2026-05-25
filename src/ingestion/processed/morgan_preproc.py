"""One-off preprocessor for Morgan et al. (Handbook of Causal Analysis).

Source OCR uses single `#` for every header. Chapter starts as `# Chapter N`
(sometimes with title on same line, sometimes title on a separate `# ...` line
that follows). Sections inside chapters are flat `# Title`.

Transforms:
1. Keep `# Chapter N ...` lines as H1.
2. If a `# Chapter N` line has no title attached, merge the immediately following
   `# Title` line into it (skip blanks).
3. Promote every other `# X` to `## X`.
4. Dedupe consecutive duplicate headers (normalized).

Output: library/_processed/morgan_fixed.md
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(
    "/home/iohan/Documents/Converters/Cloud based/Converters/Files/Output/"
    "Causal Inference/2013_Morgan_etal/vlm/2013_Morgan_etal.md"
)
DST = Path(__file__).parent / "morgan_fixed.md"

RE_CHAPTER_HEAD = re.compile(r"^# Chapter (\d+)\s*(.*)$")
RE_H1 = re.compile(r"^# (.+?)\s*$")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main() -> None:
    lines = SRC.read_text().splitlines()
    out: list[str] = []
    prev_norm: str | None = None
    promoted = 0
    kept_ch = 0
    merged = 0
    dedup = 0

    i = 0
    while i < len(lines):
        ln = lines[i]
        m_ch = RE_CHAPTER_HEAD.match(ln)
        if m_ch:
            num = m_ch.group(1)
            title = m_ch.group(2).strip()
            if not title:
                # Look ahead for the next `# X` line, skipping blanks.
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    m_next = RE_H1.match(lines[j])
                    if m_next:
                        title = m_next.group(1).strip()
                        i = j  # consume the title line
                        merged += 1
            header = f"# Chapter {num}" + (f" {title}" if title else "")
            n = norm(header)
            if n != prev_norm:
                out.append(header)
                prev_norm = n
                kept_ch += 1
            else:
                dedup += 1
        else:
            m_h1 = RE_H1.match(ln)
            if m_h1:
                title = m_h1.group(1).strip()
                n = norm(title)
                if n == prev_norm:
                    dedup += 1
                else:
                    out.append(f"## {title}")
                    prev_norm = n
                    promoted += 1
            else:
                out.append(ln)
        i += 1

    DST.write_text("\n".join(out) + "\n")
    print(f"src lines: {len(lines)}  dst lines: {len(out)}")
    print(f"chapters kept: {kept_ch}  title-merged: {merged}  "
          f"promoted: {promoted}  dedup: {dedup}")


if __name__ == "__main__":
    main()
