"""Build structured per-chapter code records for hindsight ingestion.

One-off task script. Lives under docs/; imports nothing from src/.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CODE_EXTS = {
    ".py", ".ipynb", ".md", ".cypher", ".sql", ".txt",
    ".yaml", ".yml", ".toml", ".sh", ".js", ".ts",
}
CODE_NAMES = {"Dockerfile", "Makefile"}
NAME_PREFIXES = ("requirements",)
FILE_CAP = 100_000  # bytes read per file

_CH_RE = re.compile(r"(?i)^(?:chapter|ch)[_\s]*0*(\d+)$")


def normalize_chapter(folder_name: str) -> str | None:
    """'Chapter_13'/'chapter1'/'ch2'/'Chapter01' -> 'chNN'; else None."""
    m = _CH_RE.match(folder_name.strip())
    if not m:
        return None
    return f"ch{int(m.group(1)):02d}"


def is_code_file(name: str) -> bool:
    base = Path(name).name
    if base in CODE_NAMES:
        return True
    if any(base.lower().startswith(p) for p in NAME_PREFIXES):
        return True
    return Path(base).suffix.lower() in CODE_EXTS


_PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
_JS_IMPORT = re.compile(r"""(?:from|require\()\s*['"]([^'"]+)['"]""")


def parse_imports(src: str, lang: str) -> set[str]:
    libs: set[str] = set()
    if lang in {"js", "ts"}:
        for mod in _JS_IMPORT.findall(src):
            libs.add(mod.split("/")[0] if not mod.startswith(".") else mod)
        return {m for m in libs if not m.startswith(".")}
    for frm, imp in _PY_IMPORT.findall(src):
        mod = (frm or imp).split(",")[0].strip()
        if mod:
            libs.add(mod.split(".")[0])
    return libs


_PY_ENTITY = re.compile(r"^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)", re.M)


def parse_entities(src: str) -> list[str]:
    out: list[str] = []
    for d, c in _PY_ENTITY.findall(src):
        out.append(d or c)
    return out


def extract_notebook(text: str) -> tuple[str, str]:
    """Return (joined code cells, joined markdown cells) from .ipynb JSON."""
    nb = json.loads(text)
    code_parts, md_parts = [], []
    for cell in nb.get("cells", []):
        src = "".join(cell.get("source", []))
        if cell.get("cell_type") == "code":
            code_parts.append(src)
        elif cell.get("cell_type") == "markdown":
            md_parts.append(src)
    return "\n\n".join(code_parts), "\n\n".join(md_parts)
