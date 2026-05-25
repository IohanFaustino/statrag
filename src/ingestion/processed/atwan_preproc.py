"""One-off preprocessor for Atwan (Time Series Analysis with Python Cookbook).

Source OCR uses single `#` for every header — chapters, sections, code fences,
column listings etc. Pipeline regex_pass would treat every `#` as H1
overwriting current_h1 → zero sections.

Transform: demote every `# X` to `## X`. Pipeline will use the yaml-supplied
`chapter_title` as H1; each former H1 becomes a section. Dedupe consecutive
duplicates (page-bleed safety) WITHOUT removing lines (replace with empty so
line numbers stay aligned with the original file — yaml line ranges remain
valid).

Output: library/_processed/atwan_fixed.md
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(
    "/home/iohan/Documents/Converters/Cloud based/Converters/Files/Output/"
    "Econometrics/2026_Atwan/vlm/2026_Atwan.md"
)
DST = Path(__file__).parent / "atwan_fixed.md"

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
            # Don't reset prev_norm — only consecutive header dupes considered.

    DST.write_text("\n".join(out) + "\n")
    print(f"src lines: {len(lines)}  dst lines: {len(out)}")
    print(f"H1→H2 promoted: {promoted}  dedup (blanked): {dedup}")


if __name__ == "__main__":
    main()
