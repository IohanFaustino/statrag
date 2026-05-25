"""One-off preprocessor for MacKay (Mathematical Foundations of Machine Learning).

Source OCR uses single `#` for every header. Chapter heads as `# Chapter N: Title`.
Demote everything to `##`. Pipeline uses yaml-supplied chapter_title as H1.

Output: library/_processed/mackay_fixed.md (line numbers preserved).
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(
    "/home/iohan/Documents/Converters/Cloud based/Converters/Files/Output/"
    "Math/2024_MacKay/vlm/2024_MacKay.md"
)
DST = Path(__file__).parent / "mackay_fixed.md"

RE_H1 = re.compile(r"^# (.+?)\s*$")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main() -> None:
    lines = SRC.read_text().splitlines()
    out: list[str] = []
    prev_norm = None
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
    print(f"promoted: {promoted}  dedup: {dedup}")


if __name__ == "__main__":
    main()
