"""Preprocessor for Bellouti & Boufares (Time Series Analysis with Spark, Packt).

Source EPUB-md uses single `#` for every header — chapter numbers, chapter
titles, sections, and front/back matter alike. Pipeline regex_pass would
treat every `#` as H1 overwriting current_h1 -> zero sections.

Transform: demote every `# X` to `## X`. The yaml-supplied `chapter_title`
serves as H1; each former H1 becomes a section. Consecutive duplicates are
blanked (not removed) to preserve line numbers and yaml line ranges.

Output: spark_ts_fixed.md (sibling to this file).
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(
    "/home/iohan/Downloads/EPUB/markdown/"
    "Time Series Analysis with Spark_ A practical guide to processing, "
    "modeling, and forecasting time series with Apache Spark/"
    "Time Series Analysis with Spark_ A practical guide to processing, "
    "modeling, and forecasting time series with Apache Spark.md"
)
DST = Path(__file__).parent / "spark_ts_fixed.md"

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
                out.append("")
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
