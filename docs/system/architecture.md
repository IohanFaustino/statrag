# Architecture

## Pipeline (5 stages per chapter)

```
Stage A  static metadata
  ingestion/books/<slug>.yaml  +  data/parsed/<slug>/book.json
  └─ index_terms, bibliography, authors

Stage B  regex extraction (deterministic)
  src/ingestion/regex_pass.py
  ├─ line-stream: tracks current_page (peek-back before line_start)
  ├─ numeric-aware hierarchy: headers with prefix "2.1", "2.1.1" form the
  │   backbone; unnumbered headers ("Prediction") become leaf subsections of
  │   the last numbered ancestor
  ├─ h2_path joined with " | " (PATH_SEP), e.g.
  │   "2.1 What Is Statistical Learning? | 2.1.1 Why Estimatef? | Prediction"
  ├─ H1 fallback = chapter_title from yaml
  └─ emits SectionMetadata[]; extract_images() pairs <img> with FIGURE caption

Stage C  LLM enrichment (per section, cached)
  src/ingestion/llm_enrich.py
  ├─ provider factory (openai gpt-5.4-nano-2026-03-17 | deepseek)
  ├─ 1-shot prompt, strict JSON schema
  └─ outputs synopsis (str) + index_extended (list[str])

Stage D  chunking (single-tier)
  src/ingestion/build_documents.py
  ├─ tiktoken cl100k_base
  ├─ section <= 8000 tokens -> 1 chunk
  ├─ section >  8000 tokens -> N chunks of 8000, overlap 200
  └─ BuildStats: token histogram, oversize count, per-section breakdown

Stage E  persistence
  src/ingestion/pipeline.py
  ├─ Qdrant text collection: named vectors (text 3072d dense + bm25 sparse)
  ├─ Qdrant image collection: caption embedding (3072d)
  └─ manifest write (skipped if limit_sections != None)
```

## Vector store: Qdrant

Two collections:

| Collection | Vector(s) | Purpose |
|---|---|---|
| `introduction_textbooks` | `text` (3072d dense, cosine) + `bm25` (sparse) | Hybrid section-level RAG, native RRF fusion |
| `introduction_images` | `caption` (3072d dense, cosine) | Figure search by caption embedding |

Dashboard: `http://localhost:6333/dashboard`.

## Payload schema (text collection)

```
book, book_slug, book_name, authors, theme   # `book` alias = book_slug
                                              # `theme` from yaml (e.g. "Machine Learning")
chapter_id, section_id                   # filter + dedupe
h1, h2_path                              # navigation
page_from, page_to                       # citation
token_count, chunk_index, n_chunks_in_section
has_formula, has_image, has_table, n_formulas
synopsis (str, 500 chars max)
index_extended (csv, 20 terms max)
text (chunk content)
chunk_id (deterministic md5)
```

## Payload schema (image collection)

```
book, book_slug, book_name, authors, theme
chapter_id, section (h1), subsection (h2_path), page
image_name, image_path, image_reference (full FIGURE caption)
```

## Retrieval

```
src/retrievers.py:QdrantHybridRetriever
  ├─ dense query (OpenAI embed) + sparse query (fastembed Qdrant/bm25)
  └─ Qdrant Prefetch + FusionQuery(Fusion.RRF) — server-side fusion
src/retrievers.py:search_images
  └─ direct query against caption vector
```

Chain (`src/services/retrieval/chain.py:build_chain`):
```
{question} -> retriever -> top_k chunks
                       -> prompt (system + context + question)
                       -> ChatOpenAI gpt-5.4-nano-2026-03-17
                       -> {answer, sources}
```

## Chat service (Part 2) — services layer

`src/services/chat/` adds an SSE-streaming chat backbone on top of the retrieval pipeline. Chinese-wall compliant: imports only `src.core.*`.

```
web/ (React+Vite+TS SPA) ──fetch+SSE──▶ src/services/chat/api.py (FastAPI)
                                          ├─ books.py       (registry from manifest+yamls)
                                          ├─ retrieval.py   (hybrid RRF, multi-collection fan-out)
                                          ├─ highlights.py  (sentence-level rerank)
                                          ├─ llm/router.py  (OpenAI + DeepSeek async streaming)
                                          ├─ store.py       (SQLite data/chat.db)
                                          ├─ rewriter.py    (v1 heuristic)
                                          ├─ orchestrator.py (rewrite → retrieve → LLM stream → SSE)
                                          └─ prompts/tutor.py
```

Collection mapping: demo assumed per-BOOK collections; reality is per-FIELD (`<field>_textbooks`). `books.collections_for_books(slugs)` groups requested books by field and emits `book_slug IN [...]` payload filters. Frontend never touches collection names.

SSE event surface (v1 + v2): `meta` → `token`/`paragraph_break`/`math_block`/`figure`/`source_chip` → `sources_full` → `figures_full` → `retrieval_meta` → `usage` → `done` (or `error` + `done`). The terminal `usage` event carries `durationMs`, `promptChars`, `completionChars`, `estTokens` (char-based heuristic, not a real model usage count).

Auxiliary route `GET /api/figures?path=<urlencoded>` serves whitelisted image files (roots: `/home/iohan/Documents/Books`, repo `data/`) for figure previews; `retrieval._chart_url` builds those URLs from payload `image_path`.

Operational doc: [`docs/services/chat.md`](../services/chat.md).

## Chunking constants

In `src/ingestion/build_documents.py`:

| Constant | Value | Purpose |
|---|---|---|
| `TARGET_TOKENS` | 8000 | Per-chunk soft cap, matches embedding input limit |
| `OVERLAP_TOKENS` | 200 | Sliding window overlap when section is split |
| `HARD_MAX_TOKENS` | 8190 | Safety cap below the 8191 embedding limit |

Tokenizer: `tiktoken.get_encoding("cl100k_base")` (matches `text-embedding-3-large` and `gpt-4*` family).

## Models (from `.env`)

| Var | Value | Used for |
|---|---|---|
| `OPENAI_EMBED_MODEL` | `text-embedding-3-large` | Dense text + image-caption vectors (3072d) |
| `OPENAI_MODEL_NANO` | `gpt-5.4-nano-2026-03-17` | RAG answer + LLM enrichment (default) |
| `OPENAI_MODEL_FULL` | `gpt-5.4-2026-03-05` | Reserved for future heavy-context tasks (1M ctx) |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | Alternative enrichment provider |

## Manifest (`data/parsed/manifest.json`)

Tracks `(book_slug, chapter_id)` tuples already ingested. Skip rule:
- Same `chapter_hash` AND `status=success` → skip.
- Otherwise → re-ingest.

Preview runs (`limit_sections != None`) DO NOT write to the manifest.

## Idempotency layers

| Layer | Granularity | Where | Effect |
|---|---|---|---|
| 1. Manifest | (book, chapter) | `data/parsed/manifest.json` | Skip BEFORE any LLM/embed call |
| 2. LLM cache | section_id + provider + payload_hash | `data/parsed/<slug>/cache/` | Skip re-prompting same content |
| 3. Qdrant point IDs | chunk_id (UUIDv5 of content md5) | Qdrant | Upsert overwrites same id; no duplicates |
