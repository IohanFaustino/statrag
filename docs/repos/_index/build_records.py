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


_PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.,\t ]+))", re.M)
_JS_IMPORT = re.compile(r"""(?:from|require\()\s*['"]([^'"]+)['"]""")


def parse_imports(src: str, lang: str) -> set[str]:
    libs: set[str] = set()
    if lang in {"js", "ts"}:
        for mod in _JS_IMPORT.findall(src):
            libs.add(mod.split("/")[0] if not mod.startswith(".") else mod)
        return {m for m in libs if not m.startswith(".")}
    for frm, imp in _PY_IMPORT.findall(src):
        if frm:
            # "from X import a, b" — only the module X matters
            libs.add(frm.split(".")[0])
        else:
            # "import os, sys" — each comma-separated name is a module
            for part in imp.split(","):
                mod = part.strip()
                if mod:
                    # strip trailing " as <alias>" if present
                    mod = mod.split(" as ")[0].strip()
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


# ---------------------------------------------------------------------------
# Emitter — per-chapter entry builder + markdown renderer + build_all driver
# ---------------------------------------------------------------------------

LANG_BY_EXT = {
    ".py": "py", ".ipynb": "py", ".js": "js", ".ts": "ts",
    ".cypher": "cypher", ".sql": "sql", ".sh": "bash",
    ".md": "md", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:FILE_CAP]
    except Exception:
        return ""


def _read_full(path: Path) -> str:
    """Read a file without the FILE_CAP byte limit (used for .ipynb only)."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def build_chapter_entry(slug, chapter, title, repo, branch, folder: Path) -> dict:
    files, libraries, entities = [], set(), {}
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or not is_code_file(p.name):
            continue
        if ".git" in p.parts or "node_modules" in p.parts:
            continue
        rel = str(p.relative_to(folder))
        ext = p.suffix.lower()
        lang = LANG_BY_EXT.get(ext, "")
        if ext == ".ipynb":
            raw = _read_full(p)
            try:
                code, _md = extract_notebook(raw) if raw else ("", "")
            except Exception:
                code = ""
            libraries |= parse_imports(code, "py")
            ents = parse_entities(code)
        else:
            raw = _read(p)
            if ext == ".py":
                libraries |= parse_imports(raw, "py")
                ents = parse_entities(raw)
            elif ext in {".js", ".ts"}:
                libraries |= parse_imports(raw, lang)
                ents = []
            else:
                ents = []
        if ents:
            entities[rel] = ents
        files.append({"path": rel, "lang": lang or ext.lstrip(".")})
    return {
        "slug": slug, "chapter": chapter, "title": title,
        "repo": repo, "branch": branch, "folder": folder.name,
        "files": files, "libraries": sorted(libraries), "entities": entities,
    }


def render_record(book: str, slug: str, entry: dict) -> str:
    ch = entry["chapter"]
    lines = [
        f"# code:{slug}:{ch} — {entry['title']}",
        "",
        f"book: {book}",
        f"slug: {slug}",
        f"chapter: {ch}",
        f"chapter_title: {entry['title']}",
        f"repo: {entry['repo']} (branch {entry['branch']})",
        f"folder: {entry['folder']}",
        "",
        "## Summary",
        "<!-- AUTHOR:summary — 2-4 sentences on what this chapter's code does -->",
        "",
        "## Libraries & frameworks",
        ", ".join(entry["libraries"]) or "(none detected)",
        "",
        "## Models & APIs",
        "<!-- AUTHOR:models — models/APIs used, e.g. gpt-4o, text-embedding-3-large -->",
        "",
        "## Concepts / patterns",
        "<!-- AUTHOR:concepts — patterns demonstrated, tie to book theme -->",
        "",
        "## Files",
    ]
    for f in entry["files"]:
        lines.append(f"- {f['path']} — <!-- AUTHOR:purpose --> ({f['lang']})")
    lines += ["", "## Code entities"]
    if entry["entities"]:
        for path, ents in entry["entities"].items():
            lines.append(f"- {path}: {', '.join(ents)}")
    else:
        lines.append("(none detected)")
    lines += ["", "## Key snippets",
              "<!-- AUTHOR:snippets — paste a few short representative blocks -->", ""]
    return "\n".join(lines)


REPOS = {
    "agentic_patterns": ("https://github.com/PacktPublishing/Agentic-Architectural-Patterns-for-Building-Multi-Agent-Systems", "main"),
    "langchain_genai": ("https://github.com/benman1/generative_ai_with_langchain", "second_edition"),
    "neo4j_llm": ("https://github.com/PacktPublishing/Building-Neo4j-Powered-Applications-with-LLMs", "main"),
    "rothman_rag": ("https://github.com/Denis2054/RAG-Driven-Generative-AI", "main"),
}

ROOT = Path("/home/iohan/Documents/toolbox/AI_models/RAG")


def _load_book(slug: str) -> dict:
    import yaml
    data = yaml.safe_load((ROOT / f"src/ingestion/books/{slug}.yaml").read_text())
    return data


def build_all() -> dict:
    here = ROOT / "docs/repos"
    rec_dir = here / "_index/records"
    rec_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"books": {}}
    for slug, (repo, branch) in REPOS.items():
        book = _load_book(slug)
        name = book["name"]
        chapters = book.get("chapters", {})
        repo_dir = here / slug
        folder_by_ch = {}
        for sub in sorted(p for p in repo_dir.iterdir() if p.is_dir()):
            ch = normalize_chapter(sub.name)
            if ch:
                folder_by_ch[ch] = sub
        book_entry = {"name": name, "repo": repo, "branch": branch, "chapters": {}}
        for ch, meta in chapters.items():
            title = meta["title"] if isinstance(meta, dict) else str(meta)
            if ch in folder_by_ch:
                entry = build_chapter_entry(slug, ch, title, repo, branch, folder_by_ch[ch])
                rec_path = rec_dir / f"{slug}__{ch}.md"
                rec_path.write_text(render_record(name, slug, entry))
                book_entry["chapters"][ch] = {
                    "title": title, "status": "code",
                    "folder": entry["folder"],
                    "n_files": len(entry["files"]),
                    "libraries": entry["libraries"],
                    "record": f"_index/records/{rec_path.name}",
                }
            else:
                book_entry["chapters"][ch] = {"title": title, "status": "no-code"}
        for ch, sub in folder_by_ch.items():
            if ch not in chapters:
                book_entry["chapters"].setdefault(ch, {
                    "title": "(unmapped repo folder)", "status": "unmapped",
                    "folder": sub.name,
                })
        manifest["books"][slug] = book_entry
    (here / "_index/manifest.json").write_text(json.dumps(manifest, indent=2))
    _write_index(here, manifest)
    return manifest


def _write_index(here: Path, manifest: dict) -> None:
    rows = ["# Companion Code Index", "",
            "Generated by `_index/build_records.py`. Maps book chapters to cloned repo code.",
            "", "| Book | Chapter | Title | Status | Folder | Files | Libraries |",
            "|---|---|---|---|---|---|---|"]
    for slug, b in manifest["books"].items():
        for ch, c in sorted(b["chapters"].items()):
            libs = ", ".join(c.get("libraries", [])[:6])
            rows.append(
                f"| {slug} | {ch} | {c['title']} | {c['status']} | "
                f"{c.get('folder','—')} | {c.get('n_files','—')} | {libs} |"
            )
    (here / "INDEX.md").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    m = build_all()
    n = sum(1 for b in m["books"].values()
            for c in b["chapters"].values() if c["status"] == "code")
    print(f"Wrote {n} chapter records across {len(m['books'])} books.")
