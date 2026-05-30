# Book-Chapter ↔ Code → Hindsight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract each GenAI textbook chapter's companion code into structured, entity-rich records and ingest them into the hindsight `claude-code` bank with a queryable index.

**Architecture:** A deterministic Python builder (`docs/repos/_index/build_records.py`) walks the four cloned repos, maps code folders to book chapters by number, extracts file trees / libraries / code entities / notebook prose, and emits one markdown record per chapter (with author placeholders), a `manifest.json`, and a human `INDEX.md`. The agent then authors the analytic fields per chapter, ingests each finalized record via the hindsight MCP `agent_knowledge_ingest` tool, creates an auto-rebuilding `book-code-index` page, and verifies recall.

**Tech Stack:** Python 3.12 stdlib + PyYAML (via `.venv`), pytest, hindsight MCP plugin (`agent_knowledge_ingest` / `agent_knowledge_create_page` / `agent_knowledge_recall`, bank `claude-code`).

**Spec:** `docs/superpowers/specs/2026-05-30-book-code-hindsight-design.md`

---

## File Structure

- `docs/repos/_index/build_records.py` — builder: pure extraction helpers + emitter + CLI.
- `docs/repos/_index/test_build_records.py` — pytest for the pure helpers + emitter on a fixture.
- `docs/repos/_index/records/<slug>__chNN.md` — generated structured records (30).
- `docs/repos/_index/manifest.json` — generated mapping.
- `docs/repos/INDEX.md` — generated human index.

Run interpreter: `/home/iohan/Documents/toolbox/AI_models/RAG/.venv/bin/python`.
All commands assume repo root `cd /home/iohan/Documents/toolbox/AI_models/RAG`.

---

## Task 1: Pure extraction helpers (TDD)

**Files:**
- Create: `docs/repos/_index/build_records.py`
- Test: `docs/repos/_index/test_build_records.py`

- [ ] **Step 1: Write the failing tests**

```python
# docs/repos/_index/test_build_records.py
import json
import build_records as br


def test_normalize_chapter_folder_variants():
    assert br.normalize_chapter("Chapter_13") == "ch13"
    assert br.normalize_chapter("chapter1") == "ch01"
    assert br.normalize_chapter("ch2") == "ch02"
    assert br.normalize_chapter("Chapter01") == "ch01"
    assert br.normalize_chapter("commons") is None
    assert br.normalize_chapter("writing_assistant") is None
    assert br.normalize_chapter(".git") is None


def test_whitelist_and_skip():
    assert br.is_code_file("a.py")
    assert br.is_code_file("notebook.ipynb")
    assert br.is_code_file("Dockerfile")
    assert br.is_code_file("requirements.txt")
    assert not br.is_code_file("data.csv")
    assert not br.is_code_file("fig.png")
    assert not br.is_code_file("model.pkl")


def test_parse_imports_python():
    src = "import os\nfrom langchain.chat_models import ChatOpenAI\nimport neo4j.graph\n"
    assert br.parse_imports(src, "py") == {"os", "langchain", "neo4j"}


def test_parse_imports_js():
    src = "import { foo } from 'langchain';\nconst x = require('neo4j-driver');\n"
    assert br.parse_imports(src, "js") == {"langchain", "neo4j-driver"}


def test_parse_entities_python():
    src = "import x\n\ndef build_graph():\n    pass\n\nclass Retriever:\n    def m(self): pass\n"
    assert br.parse_entities(src) == ["build_graph", "Retriever"]


def test_extract_notebook_cells():
    nb = json.dumps({
        "cells": [
            {"cell_type": "markdown", "source": ["# Title\n", "text"]},
            {"cell_type": "code", "source": ["import langchain\n", "x=1"]},
            {"cell_type": "raw", "source": ["ignore"]},
        ]
    })
    code, md = br.extract_notebook(nb)
    assert "import langchain" in code
    assert "# Title" in md
    assert "ignore" not in code and "ignore" not in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd docs/repos/_index && /home/iohan/Documents/toolbox/AI_models/RAG/.venv/bin/python -m pytest test_build_records.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_records'` / attributes missing.

- [ ] **Step 3: Implement the helpers**

```python
# docs/repos/_index/build_records.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd docs/repos/_index && /home/iohan/Documents/toolbox/AI_models/RAG/.venv/bin/python -m pytest test_build_records.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
git add docs/repos/_index/build_records.py docs/repos/_index/test_build_records.py
git commit -m "feat(repos): add code-record extraction helpers + tests"
```

---

## Task 2: Emitter — records + manifest + INDEX (TDD on a fixture)

**Files:**
- Modify: `docs/repos/_index/build_records.py` (append `build_chapter_entry`, `render_record`, `build_all`, CLI)
- Modify: `docs/repos/_index/test_build_records.py` (add emitter test)

- [ ] **Step 1: Write the failing test**

```python
# append to test_build_records.py
def test_build_chapter_entry_and_render(tmp_path):
    folder = tmp_path / "Chapter01"
    folder.mkdir()
    (folder / "graph.py").write_text(
        "from neo4j import GraphDatabase\n\ndef build_graph():\n    pass\n"
    )
    (folder / "README.md").write_text("# Ch1\nBuilds a graph.\n")

    entry = br.build_chapter_entry(
        slug="demo", chapter="ch01", title="Graphs",
        repo="http://example/repo", branch="main", folder=folder,
    )
    assert entry["chapter"] == "ch01"
    assert "neo4j" in entry["libraries"]
    assert "build_graph" in entry["entities"]["graph.py"]
    assert any(f["path"] == "graph.py" for f in entry["files"])

    md = br.render_record(book="Demo Book", slug="demo", entry=entry)
    assert "code:demo:ch01" in md
    assert "AUTHOR:summary" in md
    assert "neo4j" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd docs/repos/_index && /home/iohan/Documents/toolbox/AI_models/RAG/.venv/bin/python -m pytest test_build_records.py::test_build_chapter_entry_and_render -v`
Expected: FAIL — `AttributeError: module 'build_records' has no attribute 'build_chapter_entry'`.

- [ ] **Step 3: Implement the emitter (append to build_records.py)**

```python
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
        raw = _read(p)
        if ext == ".ipynb":
            code, _md = extract_notebook(raw) if raw else ("", "")
            libraries |= parse_imports(code, "py")
            ents = parse_entities(code)
        elif ext == ".py":
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd docs/repos/_index && /home/iohan/Documents/toolbox/AI_models/RAG/.venv/bin/python -m pytest test_build_records.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
git add docs/repos/_index/build_records.py docs/repos/_index/test_build_records.py
git commit -m "feat(repos): emitter for records, manifest, and INDEX"
```

---

## Task 3: Generate records for all repos

**Files:**
- Generates: `docs/repos/_index/records/*.md`, `docs/repos/_index/manifest.json`, `docs/repos/INDEX.md`

- [ ] **Step 1: Run the builder**

Run: `cd /home/iohan/Documents/toolbox/AI_models/RAG && .venv/bin/python docs/repos/_index/build_records.py`
Expected: prints `Wrote 30 chapter records across 4 books.`

- [ ] **Step 2: Verify coverage**

Run: `cd /home/iohan/Documents/toolbox/AI_models/RAG && .venv/bin/python -c "import json;m=json.load(open('docs/repos/_index/manifest.json'));print({s:sum(1 for c in b['chapters'].values() if c['status']=='code') for s,b in m['books'].items()})"`
Expected: `{'agentic_patterns': 3, 'langchain_genai': 9, 'neo4j_llm': 8, 'rothman_rag': 10}`

If counts differ, inspect `manifest.json` for `unmapped`/`no-code` flags and fix folder→chapter mapping in `normalize_chapter` or the repo layout assumptions before continuing.

- [ ] **Step 3: Spot-check one record**

Run: `cat docs/repos/_index/records/neo4j_llm__ch02.md`
Expected: header fields populated, `## Libraries` lists real packages (e.g. `neo4j`), AUTHOR placeholders present.

- [ ] **Step 4: Commit generated artifacts**

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
git add docs/repos/_index/records docs/repos/_index/manifest.json docs/repos/INDEX.md
git commit -m "chore(repos): generate skeleton code records + manifest + index"
```

---

## Tasks 4–7: Author + ingest per book

> One task per book. For each chapter record: read the repo folder's code, replace every `<!-- AUTHOR:* -->` placeholder with real analytic content, then ingest the finalized record. This is agent-driven (reading + authoring + MCP tool calls), not a code change.

### Per-chapter procedure (applies to every chapter in Tasks 4–7)

- [ ] **A. Read the code:** open the chapter's repo folder (paths from the record's `folder:` + `## Files`). Skim each code file and the README/notebook markdown.
- [ ] **B. Edit the record** `docs/repos/_index/records/<slug>__chNN.md`, replacing placeholders:
  - `AUTHOR:summary` → 2–4 sentences: what the chapter's code builds/demonstrates.
  - `AUTHOR:models` → concrete models/APIs (e.g. `gpt-4o`, `text-embedding-3-large`, `neo4j-aura`); `(none)` if truly none.
  - `AUTHOR:concepts` → patterns tied to the book theme (e.g. `GraphRAG`, `multi-agent orchestration`, `hybrid retrieval`).
  - each `AUTHOR:purpose` → one-line purpose for that file.
  - `AUTHOR:snippets` → 1–3 short representative blocks (≤ ~30 lines each), fenced with language.
- [ ] **C. Verify no placeholder remains:**
  Run: `! grep -q "AUTHOR:" docs/repos/_index/records/<slug>__chNN.md && echo clean`
  Expected: `clean`
- [ ] **D. Ingest** via MCP: `agent_knowledge_ingest(title="code:<slug>:chNN", content=<full finalized record text>)`.

### Task 4: rothman_rag (10 chapters: ch01–ch10)
- [ ] Run the per-chapter procedure for ch01…ch10.
- [ ] Commit: `git add docs/repos/_index/records/rothman_rag__*.md && git commit -m "docs(repos): author rothman_rag chapter code records"`

### Task 5: langchain_genai (9 chapters: ch01–ch09)
- [ ] Run the per-chapter procedure for ch01…ch09.
- [ ] Commit: `git add docs/repos/_index/records/langchain_genai__*.md && git commit -m "docs(repos): author langchain_genai chapter code records"`

### Task 6: neo4j_llm (8 chapters: ch02,03,04,05,06,07,09,12)
- [ ] Run the per-chapter procedure for each present chapter.
- [ ] Commit: `git add docs/repos/_index/records/neo4j_llm__*.md && git commit -m "docs(repos): author neo4j_llm chapter code records"`

### Task 7: agentic_patterns (3 chapters: ch13,14,15)
- [ ] Run the per-chapter procedure for ch13,14,15.
- [ ] Commit: `git add docs/repos/_index/records/agentic_patterns__*.md && git commit -m "docs(repos): author agentic_patterns chapter code records"`

---

## Task 8: Create index page + verify recall

- [ ] **Step 1: Confirm bank**

MCP: `agent_knowledge_get_current_bank()` → expect `claude-code`.

- [ ] **Step 2: Create the standing index page**

MCP: `agent_knowledge_create_page(page_id="book-code-index", name="Book Companion Code Index", source_query="Which textbook chapters have companion code, in which repo and folder, which libraries and models do they use, and what does each implement?")`

- [ ] **Step 3: Verify recall returns the right records**

MCP: `agent_knowledge_recall(query="neo4j GraphRAG companion code chapter", max_tokens=1024)`
Expected: result references a `code:neo4j_llm:chNN` record.

MCP: `agent_knowledge_recall(query="LangChain agent code example chapter", max_tokens=1024)`
Expected: result references a `code:langchain_genai:chNN` record.

If recall misses, confirm the ingests succeeded (re-ingest the missing title) before proceeding.

- [ ] **Step 4: List pages to confirm index exists**

MCP: `agent_knowledge_list_pages()` → expect `book-code-index` present.

---

## Task 9: Finalize docs + memory

- [ ] **Step 1: Update the genai library note**

Add a short paragraph to `docs/library/genai_textbooks.md` under `## Notes`: companion code for all four books cloned to `docs/repos/<slug>/`, structured per-chapter records under `docs/repos/_index/records/`, ingested into hindsight bank `claude-code` (titles `code:<slug>:chNN`), index page `book-code-index`, human index `docs/repos/INDEX.md`.

- [ ] **Step 2: Write a project memory**

Create `/home/iohan/.claude/projects/-home-iohan-Documents-toolbox-AI-models-RAG/memory/book-code-hindsight.md` (type: project): the 30 chapter code records live in hindsight bank `claude-code` under titles `code:<slug>:chNN`, rebuilt via `docs/repos/_index/build_records.py`, indexed by page `book-code-index`. Link `[[hindsight-memory-server]]` and `[[genai-field-and-kobo-preproc]]`. Add the one-line pointer to `MEMORY.md`.

- [ ] **Step 3: Commit**

```bash
cd /home/iohan/Documents/toolbox/AI_models/RAG
git add docs/library/genai_textbooks.md
git commit -m "docs(library): note companion code records in hindsight"
```

---

## Self-Review notes

- **Spec coverage:** mapping (T2 `build_all`), builder/extraction (T1–T2), structured record template (T2 `render_record`), full-source-as-snippets (per-chapter author step D + `AUTHOR:snippets`), ingestion (T4–T7 step D), index page + INDEX.md (T2 `_write_index`, T8), retrieval keys & verification (T8). All spec sections map to tasks.
- **No-code / unmapped chapters:** handled in `build_all` (status `no-code` / `unmapped`), surfaced in INDEX.md, never ingested — matches spec "Out of scope".
- **Type consistency:** `build_chapter_entry` returns the `entry` dict consumed by `render_record` and `build_all`; manifest keys (`status`, `folder`, `n_files`, `libraries`, `record`) consistent across emitter and `_write_index`.
