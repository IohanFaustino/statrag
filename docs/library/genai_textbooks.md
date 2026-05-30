# `genai_textbooks`

Qdrant collection: `genai_textbooks` (paired with `genai_images`).
Field: `genai`.

GenAI / LLM-application / agent engineering. First field ingested with the
DeepSeek provider (`deepseek-v4-flash`) instead of OpenAI for synopsis
enrichment; embeddings remain OpenAI `text-embedding-3-large`.

## Books

| Slug | Name | Authors | Year | Edition | Theme | Chapters | Chunks | Images |
|---|---|---|---|---|---|---|---|---|
| `neo4j_llm` | Building Neo4j-Powered Applications with LLMs | Ravindranatha Anthapu, Siddhant Agarwal | 2025 | 1st | Knowledge Graphs | 13 | 171 | 0 |
| `rothman_rag` | RAG-Driven Generative AI | Denis Rothman | 2024 | 1st | RAG | 10 | 267 | 0 |
| `langchain_genai` | Generative AI with LangChain | Ben Auffarth, Leonid Kuligin | 2025 | 2nd | LLM App Development | 10 | 276 | 0 |
| `agentic_patterns` | Agentic Architectural Patterns for Building Multi-Agent Systems | Ali Arsanjani, Juan Pablo Bustos | 2026 | 1st | Multi-Agent Systems | 16 | 697 | 0 |

Totals: 49 chapters, 1411 chunks.

## Notes

- All four are Packt **kobo/EPUB-HTML** markdown exports, pre-processed with the
  generic `src/ingestion/processed/kobo_preproc.py` (pandoc + `kobo_filter.lua`):
  unwraps `koboSpan` markup, emits `<!-- page N -->` from arabic pagebreak
  labels, remaps semantic header classes (chapterTitle→H1, heading-1..3→H2..H4),
  merges the split chapter-number/title headings, and neutralizes code-block
  `# comment` lines so they are not mis-parsed as headers. Each yaml
  `source_path` points to `src/ingestion/processed/<slug>_fixed.md`.
- **Pages are sparse/absent** in these OCR sources: only `neo4j_llm` carries any
  page markers (22, first at p51); the other three have none. Sections without a
  nearby marker get `page_from = -1` (null). Invariant #2 (`page_from > 0`) is
  treated as **soft** for the `genai` field — content retrieval is the value,
  page citations are best-effort.
- **`images = 0`** for all four: the kobo sources reference figures as
  `./<name>.png` (book-dir root), not the `imgs/` prefix `regex_pass`/
  `extract_images` expect, so `genai_images` is empty. Text RAG is unaffected;
  image ingestion for this field is a separate future task (path mapping).
- `neo4j_llm` has a back-matter term Index extracted to
  `data/parsed/neo4j_llm/book.json` (353 `index_terms`).
- Skipped (partial samples, not full books): "30 Agents Every AI Engineer Must
  Build" (only 2 chapters) and "LLM Engineer's Handbook" (only ch1, 7, 8).
- **Companion code → hindsight**: each book's GitHub companion repo is cloned to
  `docs/repos/<slug>/` (langchain on branch `second_edition`). The builder
  `docs/repos/_index/build_records.py` maps repo code folders to book chapters by
  number and emits one structured, entity-rich record per chapter-with-code under
  `docs/repos/_index/records/<slug>__chNN.md` (+ `_index/manifest.json`,
  `docs/repos/INDEX.md`). 30 records (rothman 10, langchain 9, neo4j 8, agentic
  3) are ingested into the **hindsight** agent-memory bank `claude-code`
  (doc IDs `<slug>__chNN.md`; the `code:<slug>:chNN` key lives in each record's
  H1). Standing index = hindsight page `book-code-index`. Recall verified
  (entity extraction returns models/libraries/concepts per chapter). Spec +
  plan: `docs/superpowers/{specs,plans}/2026-05-30-book-code-hindsight*.md`. See
  [[hindsight-memory-server]].
