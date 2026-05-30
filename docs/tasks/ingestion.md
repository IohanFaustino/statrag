# Ingestion Service

Reads OCR-cleaned `.md` textbooks, splits into section-level chunks, enriches with LLM synopsis + extended index, embeds (dense + sparse + image captions), and upserts to per-field Qdrant collections.

## Where things live

| What | Path |
|---|---|
| Pipeline source | `src/ingestion/` |
| Per-book config | `src/ingestion/books/<slug>.yaml` |
| Static metadata (index + bibliography) | `data/parsed/<slug>/book.json` |
| Per-chapter outputs | `data/parsed/<slug>/<chapter>_*.json` |
| Manifest (what's ingested) | `data/parsed/manifest.json` |
| Skills | `.claude/skills/rag-add-book/`, `.claude/skills/rag-verify/` |

## Collections

Per `field` (book yaml key):

| Collection | Schema |
|---|---|
| `<field>_textbooks` | `text` (3072d dense, cosine) + `bm25` (sparse) |
| `<field>_images` | `caption` (3072d dense, cosine) |

Auto-created on first ingest of a field. Examples: `introduction_textbooks`, `econometrics_textbooks`, etc.

## Required yaml fields

`src/ingestion/books/<slug>.yaml`:

```yaml
slug: <slug>                      # short kebab id (e.g. islp, hansen)
name: <Display Name>
field: <field>                    # REQUIRED — collection prefix (e.g. introduction, econometrics)
theme: <theme string>             # free-form sub-tag, used as payload filter
authors: [First Author, Second Author]
edition: "1st"
year: 2024
source_path: <absolute path to .md>
chapters:
  ch01:
    title: <chapter title — used as h1 fallback>
    line_start: <int>             # 1-based, inclusive
    line_end: <int>               # 1-based, inclusive (or null = EOF)
```

`field` → collection routing. `theme` → payload filter.

## Ingest recipe (user-facing)

The `rag-add-book` skill follows this with gates. Direct invocation below.

### 1. Locate chapter boundaries

```bash
grep -n "^# \|^## [0-9]\|^### [0-9]\+\.1\s" /path/to/book.md | head -40
```

Each chapter's `line_end` = next chapter's `line_start - 1`.

### 2. Write yaml (see template above)

### 3. Extract static metadata (optional)

Ask Claude Code:

```
Extract static metadata from /abs/path/to/book.md into
data/parsed/<slug>/book.json.
Schema: {slug, index_terms: list[str], bibliography: list[str]}.
Use grep + Read offset/limit. DO NOT read full file.
```

### 4. Preview run (cheap)

```bash
.venv/bin/python -m src.ingestion.pipeline \
  --book <slug> --chapter ch01 --limit-sections 1 --force
```

`limit_sections != None` → manifest NOT written. Safe preview.

### 5. Inspect

```bash
jq '{n_chunks, split_sections, n_oversize, token_histogram}' \
  data/parsed/<slug>/ch01_build_stats.json
```

Expect: `n_oversize=0`, sensible histogram, no `OUTPUT_PARSING_FAILURE`.

Verify a payload sample:

```python
from src.core.qdrant_store import client, collection_names
from src.ingestion.pipeline import load_book_static_metadata
b = load_book_static_metadata("<slug>")
text_coll, _ = collection_names(b.field)
res, _ = client().scroll(text_coll, limit=3, with_payload=True,
    scroll_filter={"must":[{"key":"book","match":{"value":"<slug>"}}]})
print(res[0].payload)
# must contain: book, book_slug, book_name, theme, h1, h2_path, synopsis
```

### 6. Full ingest

```bash
for ch in ch01 ch02 ... chNN; do
  .venv/bin/python -m src.ingestion.pipeline --book <slug> --chapter $ch --force
done
```

### 7. Verify

```bash
.venv/bin/python -m src.ingestion.pipeline --status
```

Invoke `rag-verify` skill — must report 0 failures across a 50+ point sample.

## LLM provider for enrichment

Default provider is **`deepseek`** (set in `src/core/config.py`, `default_provider`,
RAG-only alias `RAG_DEFAULT_PROVIDER` — decoupled from the shared `.env`
`DEFAULT_PROVIDER` that Book_analyzer reads). Override per run with
`--provider openai`.

Ingestion DeepSeek model = **`deepseek-v4-flash`** (config `ingest_deepseek_model`,
alias `RAG_INGEST_DEEPSEEK_MODEL`). Cheapest active model ($0.14/$0.28 per 1M
in/out), enough for JSON keyword+synopsis extraction. This is **separate** from
`settings.deepseek_model` (= `deepseek-v4-pro`), which the chat long-context
organizer uses and must stay a reasoning model.

DeepSeek v4 ids default to **thinking mode** (spend output tokens on
`reasoning_content`, can return empty `content`). `llm_client.get_llm("deepseek")`
disables it via `extra_body={"thinking": {"type": "disabled"}}`.

Embeddings (dense + image) and image captioning stay on **OpenAI** — DeepSeek has
no embedding API and vision parity is unverified. OpenAI key still required.

## Cost expectation

Per ~500-page book with `openai` provider:
- Embeddings: ~$0.40
- Synopsis: ~$0.50
- Image embeddings: ~$0.01
- **Total: ~$1**

Default `deepseek` (v4-flash) for synopsis → ~$0.10 total (embeddings/images still OpenAI).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Parsed 0 sections` | OCR uses single `#` for all headers AND no numeric prefix (e.g. `# 1.1 Foo`) | Pipeline handles numeric `# N.N` since 2026-05-16. Confirm prefix exists. |
| Pydantic warning "Expected str but got list" | LLM prompt drift in synopsis | Re-check `llm_enrich.SYSTEM` rule #1 + `_coerce_synopsis` |
| `OUTPUT_PARSING_FAILURE` warnings | LaTeX backslashes in synopsis broke JSON | Section keeps other fields; only synopsis missing |
| `n_oversize > 0` | Tokenizer mismatch or split bypass | Check `build_documents.py:_split_by_tokens` |
| `page_from = None` | OCR source has no `<!-- page N -->` markers | Non-blocking; page filter won't work for that book |
| Empty `synopsis` / `index_extended` on DeepSeek | v4 model in thinking mode returned empty `content` | Ensure `ingest_deepseek_model=deepseek-v4-flash` + `extra_body` thinking-disabled in `llm_client.py`. Never point ingestion at `deepseek-v4-pro`. |
| `h1 = ""` | yaml missing `title` for that chapter | Add it |
| Empty upsert → 400 Bad Request | Chapter produced 0 sections | Pipeline guards since 2026-05-16; if still hits, regex_pass mismatched OCR style |
| Manifest skipping when re-ingest wanted | Hash matches a prior success | Use `--force` |

## Backfilling a payload field

```python
from src.core.qdrant_store import client, collection_names
from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector
qc = client()
text_coll, img_coll = collection_names("<field>")
flt = Filter(must=[FieldCondition(key="book", match=MatchValue(value="<slug>"))])
qc.set_payload(
    collection_name=text_coll,
    payload={"theme": "<theme value>"},
    points=FilterSelector(filter=flt),
    wait=True,
)
```

## Invariants

After any ingest, every text chunk payload MUST have:

- `book`, `book_slug`, `book_name`, `field`, `theme`, `h1`, `h2_path`, `chunk_id`, `text`, `synopsis`.

See [`../system/invariants.md`](../system/invariants.md) for full list.

## Skills enforce gates

`rag-add-book` skill asks at three points:
1. After yaml: extract book.json?
2. Before preview: confirm preview run?
3. After preview: confirm full ingest?

Never auto-proceed past these gates.

## Image-only ingest (`ingest_images_only`)

Add or refresh figures for a book without touching its text collection.
Useful when:

- A book's text was ingested from an old markdown source but figures
  weren't extracted (e.g. ISLP legacy path, EPUB books).
- A new VLM-format markdown is available and only its figures need to
  be added to Qdrant.

### Usage

```bash
# auto-detects format (VLM vs EPUB) from first image ref
.venv/bin/python -m src.ingestion.ingest_images_only \
    --book <slug> \
    --md /path/to/<book>.md

# dry-run: extract + report counts, no writes
.venv/bin/python -m src.ingestion.ingest_images_only --book <slug> --md ... --dry-run
```

Flags:

| Flag | Default | Meaning |
|---|---|---|
| `--book` | required | yaml slug under `src/ingestion/books/` |
| `--md` | required | path to markdown source |
| `--format` | `auto` | `vlm`/`epub`/`auto` — `auto` inspects first image ref |
| `--dry-run` | off | extract + log, no Qdrant writes |

### Supported markdown formats

| Format | Image ref pattern | Caption source |
|---|---|---|
| `vlm` | `![](images/<sha>.jpg)` | nearest `<details><summary>...</summary>...</details>` + preceding prose |
| `epub` | `![alt](markdown/<title>/media/.../*.jpg)` | following italicised line (`*Figure x.x: ...*`) or alt text |

The EPUB extractor skips inline-math `Art_P*.jpg` glyphs (alt = `art`).

### Writes

- Upserts to `<field>_images` collection (chunked at 100 points per
  batch to avoid Qdrant write timeouts).
- IDs are deterministic (`UUID5(book_slug::image_name)`); re-running is
  idempotent.
- Registers a manifest entry with `chapter_id="images_only"`,
  `chunk_count=0`, `image_count=N`, so `--status` / `rag-verify` see it.

### Preflight

Audit which books are ready for image-only ingest:

```bash
.venv/bin/python ops/scripts/preflight_image_ingest.py
```

Output → `data/parsed/_ingest_audit.json` + a per-book table on stdout
showing vlm-md path, on-disk image count, in-markdown ref count, and
current image collection size.

### Path resolution gotcha (EPUB books)

EPUB-converted markdown references images under
`markdown/<Book Title>/media/.../*.jpg` relative to the markdown's
parent. Original image files live at
`/home/iohan/Downloads/EPUB/markdown/...`. A symlink

```
src/ingestion/processed/markdown -> /home/iohan/Downloads/EPUB/markdown
```

resolves these refs for `_make_image`'s
`book_dir / img_path` fallback. Don't delete the symlink.
