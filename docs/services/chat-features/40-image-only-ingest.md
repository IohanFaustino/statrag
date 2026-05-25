# 40 — Image-only ingest pipeline

> Companion to feature [39 — image judge](39-image-judge.md). Feature 39
> assumes a populated `<field>_images` collection; this feature
> documents *how* those collections get populated **without** touching
> the paired text collection.

## Purpose

Add or refresh figures for a book whose text was already ingested.
Used to grow the image library from 1 → 25 books (271 → 8083 pts
across 6 collections) without re-running the heavier text-side
embedding pass.

## Pipeline

```mermaid
graph TD
  Y[book yaml<br/>slug, field, source_path] --> P[preflight<br/>ops/scripts/preflight_image_ingest.py]
  P -->|audit JSON| U[user reviews ready/missing]
  U --> R{format?}
  R -->|VLM output| V[extract_vlm_images<br/>!\[\]\(images/&lt;sha&gt;\) + &lt;details&gt;]
  R -->|EPUB-md| E[extract_epub_images<br/>!\[alt\]\(markdown/&lt;title&gt;/...\) + italic caption]
  V --> M[ImageMetadata list]
  E --> M
  M --> EM["embed captions<br/>text-embedding-3-large"]
  EM --> Q["_persist_images<br/>BATCH=100 chunked upsert<br/>&lt;field&gt;_images"]
  Q --> MAN[manifest.register<br/>chapter_id='images_only']
```

## Files

| Path | Role |
|---|---|
| `src/ingestion/ingest_images_only.py` | CLI entry + `extract_vlm_images` + `extract_epub_images` + caption builders |
| `src/ingestion/pipeline.py:_persist_images` | Chunked upsert (BATCH=100) |
| `ops/scripts/preflight_image_ingest.py` | Read-only audit, writes `data/parsed/_ingest_audit.json` |
| `src/ingestion/processed/markdown` | Symlink → `/home/iohan/Downloads/EPUB/markdown` so EPUB image refs resolve |

## Usage

```bash
# preflight (read-only)
.venv/bin/python ops/scripts/preflight_image_ingest.py

# dry-run (extract + log, no Qdrant writes)
.venv/bin/python -m src.ingestion.ingest_images_only \
    --book hansen \
    --md /path/to/2022_Hansen.md \
    --dry-run

# live
.venv/bin/python -m src.ingestion.ingest_images_only \
    --book hansen \
    --md /path/to/2022_Hansen.md
```

Flags:

| Flag | Default | Meaning |
|---|---|---|
| `--book` | required | yaml slug |
| `--md` | required | path to markdown source |
| `--format` | `auto` | `vlm` / `epub` / `auto` |
| `--dry-run` | off | extract + log, no Qdrant writes |

## Supported markdown formats

| Format | Image ref pattern | Caption source | Filter |
|---|---|---|---|
| `vlm` | `![](images/<sha>.jpg)` | nearest `<details><summary>…</summary>…</details>` + preceding prose | — |
| `epub` | `![alt](markdown/<title>/media/…/*.jpg)` | following italic line `*Figure x.x: …*` or alt text | `Art_P*.jpg` skipped when alt is `art` (inline-math glyphs) |

## Caption building

1. **Preceding prose** — last 1–2 sentences of the paragraph before the
   image. Skips headers, image refs, html tags, table rows, lines < 20
   chars.
2. **VLM `<details>` block** — concatenated `summary` + first 200
   chars of body (HTML stripped, table separators normalised).
3. **EPUB italic-line** — `*Figure x.x: …*` match within 1500 chars
   after the image.
4. **Fallback** — alt text (if not `art`/`image`/`cover image`), then
   `"Figure from <book_name>"`.

Caption length capped at 600 chars.

## Chunked upsert

Single-shot upsert of 657 points timed out against Qdrant (`peck`
book). `_persist_images` now batches at 100 with `wait=True` per batch.

```
INFO src.ingestion.pipeline Qdrant image collection ... upserted batch 4/7 (100 points)
```

Idempotent: image IDs are deterministic
(`UUID5("img", f"{book_slug}::{image_name}")`). Re-runs upsert same
IDs.

## Path resolution gotcha (EPUB)

EPUB-converted markdown references images under
`markdown/<Book Title>/media/.../*.jpg`. Original files at
`/home/iohan/Downloads/EPUB/markdown/...`. Symlinked at:

```
src/ingestion/processed/markdown -> /home/iohan/Downloads/EPUB/markdown
```

`_make_image`'s fallback `book_dir / img_path` resolves through the
symlink. Don't delete it.

## Manifest tracking

Each successful image-only ingest registers a `ManifestEntry` with:

```python
chapter_id    = "images_only"
chunk_count   = 0
parent_count  = 0
image_count   = N
status        = "success"
```

so `--status` and `render_state.py` see image-only ingests.
`render_state.py` also queries Qdrant directly for live image counts
to cover books ingested before this manifest convention was added.

## Field-mapping rule

Image collection target follows the **yaml `field`**, not the on-disk
book location. Example: `hansen` lives at
`Output/Econometrics/2022_Hansen/` but `hansen.yaml` declares
`field: introduction` and `hansen` text already lives in
`introduction_textbooks` — so hansen images land in
`introduction_images` to stay consistent with the text retrieval
routing.

## Rollback / cleanup

```bash
# delete by filter (e.g. legacy "(no caption found)" stubs)
curl -X POST 'http://localhost:6333/collections/<coll>/points/delete?wait=true' \
  -H 'content-type: application/json' \
  -d '{"filter":{"must":[{"key":"image_reference","match":{"value":"(no caption found)"}}]}}'

# wipe a single book
curl -X POST 'http://localhost:6333/collections/<coll>/points/delete?wait=true' \
  -H 'content-type: application/json' \
  -d '{"filter":{"must":[{"key":"book_slug","match":{"value":"<slug>"}}]}}'
```

## Known limitations

- Caption quality for cover/title pages is weak (no preceding prose).
  The image judge filters most of these but they consume Tier-1
  attention.
- `Art_P*` filter is alt-text-driven; some books use other naming
  conventions for inline-math glyphs.
- No automatic OCR pipeline for books whose source markdown lacks
  image refs entirely.
- Manifest backfill for the 25 books ingested before this manifest
  convention was added is not automatic; new ingests register
  going-forward only.
