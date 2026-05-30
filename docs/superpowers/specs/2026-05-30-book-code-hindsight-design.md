# Book-Chapter ↔ Companion Code → Hindsight Memory

**Date**: 2026-05-30
**Status**: Approved design
**Owner**: RAG / genai field

## Goal

Associate each GenAI textbook chapter with its companion code (cloned under
`docs/repos/`), extract the code into the **format hindsight stores and
retrieves best**, ingest one structured record per (book, chapter-with-code)
into the `claude-code` hindsight bank, and build a queryable index — so the
records can later back applications.

## Why structured records, not raw code

Hindsight `ingest` runs an LLM extractor (DeepSeek-flash) that converts a
document into atomic **facts + entities + relations**, then embeds them
(`BAAI/bge-small-en-v1.5`) for semantic `recall`. Raw multi-KB source dumps
produce noisy facts, waste extraction tokens, and yield weak embeddings.
Therefore each chapter is ingested as a **structured, entity-rich
natural-language record** that the extractor can cleanly atomize, with only
short representative snippets — not whole-file blobs.

## Inventory

Four books in the `genai` field, repos cloned to `docs/repos/<slug>/`:

| Slug | Book (chapters) | Repo | Code folders | Coverage |
|---|---|---|---|---|
| `agentic_patterns` | Agentic Architectural Patterns… (16) | PacktPublishing/Agentic-Architectural-Patterns-for-Building-Multi-Agent-Systems | `Chapter_13/14/15` | 3 (use-case ch only) |
| `langchain_genai` | Generative AI with LangChain, 2nd ed (10) | benman1/generative_ai_with_langchain @ `second_edition` | `chapter1`..`chapter9` | 9 |
| `neo4j_llm` | Building Neo4j-Powered Applications with LLMs (13) | PacktPublishing/Building-Neo4j-Powered-Applications-with-LLMs | `ch2,3,4,5,6,7,9,12` | 8 (gaps) |
| `rothman_rag` | RAG-Driven Generative AI (10) | Denis2054/RAG-Driven-Generative-AI | `Chapter01`..`Chapter10` | 10 (full) |

Total chapters-with-code to ingest: **30**.

## Components

### 1. Mapping

Map repo folder → book chapter **by chapter number**: `Chapter_13`, `chapter1`,
`ch2`, `Chapter01` all normalize to `chNN`. Chapter **title** is pulled from
`src/ingestion/books/<slug>.yaml` `chapters:`.

- Folder with no matching book chapter → kept, flagged `unmapped` in manifest.
- Book chapter with no folder → omitted from bundles, listed as `no-code` in the
  index.
- Mapping is verified against each repo's README / per-chapter README where one
  exists; mismatches noted in the manifest rather than silently mapped.

### 2. Builder script — `docs/repos/_index/build_records.py`

One-off task script (Chinese-wall irrelevant: lives under `docs/`, imports
nothing in `src/`). For each chapter folder it extracts **deterministic
signals**:

- **File tree** (whitelist extensions): `.py .ipynb .md .cypher .sql .txt
  .yaml .yml .toml .sh .js .ts`, plus `Dockerfile`, `Makefile`, `requirements*`.
- **Skip**: `.git`, binaries/images/data (`.png .jpg .csv .parquet .pdf .bin
  .pkl .faiss …`), `node_modules`, virtualenvs, lockfiles.
- **`.ipynb`** → parse JSON, keep only **code + markdown cells** (drop outputs /
  notebook metadata).
- **Libraries**: regex over `import` / `from … import` / `require()` →
  deduped library list.
- **Code entities**: top-level `def` / `class` names per `.py`; exported
  symbols best-effort for `.js/.ts`.
- **Prose**: README / notebook markdown text retained verbatim.
- **Snippets**: a few short representative blocks (≤ ~30 lines each), not
  whole files; per-file hard cap ~100 KB on anything read.

Emits:

- `docs/repos/_index/records/<slug>__chNN.md` — the structured record
  (template below), with header fields, deterministic signals, prose, and
  snippet placeholders.
- `docs/repos/_index/manifest.json` — full mapping: book → chapter → folder →
  files → libraries → entities → record path → coverage flags.
- `docs/repos/INDEX.md` — human-readable index table for git/humans.

### 3. Per-chapter record template

```
# code:<slug>:chNN — <Chapter Title>

book: <Book Name>
slug: <slug>
chapter: chNN
chapter_title: <from yaml>
repo: <repo URL> (branch <branch>)
folder: <repo folder path>

## Summary
<2–4 sentences: what this chapter's code does>   ← authored (analytic)

## Libraries & frameworks
<langchain, neo4j, llamaindex, …>                  ← parsed

## Models & APIs
<gpt-4o, text-embedding-3-large, deepseek, …>      ← parsed + authored

## Concepts / patterns
<GraphRAG, multi-agent orchestration, …>           ← authored (ties to theme)

## Files
- <path> — <one-line purpose> (<language>)         ← purpose authored

## Code entities
- <file>: <funcs/classes>                           ← parsed

## Key snippets
```<lang>
<short representative block>
```
```

**Authored vs parsed**: the script fills the parsed fields deterministically;
the Summary, file purposes, Models&APIs, and Concepts are authored per chapter
(30 total) so records are genuinely analytic, not boilerplate. The script leaves
clearly marked `<!-- AUTHOR: … -->` placeholders for the authored fields.

### 4. Ingestion (driven via MCP plugin tool, `claude-code` bank)

For each finalized record:
`agent_knowledge_ingest(title="code:<slug>:chNN", content=<record md>)`.
Stable titles → re-ingest replaces. ~30 ingests.

### 5. Index element

- `agent_knowledge_create_page(page_id="book-code-index", name="Book Companion
  Code Index", source_query="Which textbook chapters have companion code, in
  which repo and folder, which libraries and models do they use, and what does
  each implement?")` — auto-rebuilding standing index consolidated from the
  ingested records.
- `docs/repos/INDEX.md` — static local mirror.

## Retrieval keys

- Title scheme `code:<slug>:chNN` — direct addressing.
- `recall("<book/topic> chapter using <library/concept>")` → the chapter
  record (entities make this strong).
- `book-code-index` page → standing overview for app bootstrapping.

## Out of scope

- Ingesting book *prose* (already in Qdrant `genai_textbooks`).
- Image/figure code.
- Chapters without companion code (listed as `no-code`, not ingested).
- A dedicated hindsight bank (using default `claude-code`).

## Success criteria

1. `manifest.json` lists all 4 books, every code folder mapped or flagged.
2. 30 structured records written under `_index/records/`.
3. All 30 ingested into `claude-code` bank; `recall` on a known library
   (e.g. "neo4j GraphRAG chapter") returns the right `code:<slug>:chNN`.
4. `book-code-index` page created; `docs/repos/INDEX.md` present and accurate.
