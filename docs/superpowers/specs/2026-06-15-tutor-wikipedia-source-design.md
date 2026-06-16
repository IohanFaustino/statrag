# Tutor mode — Wikipedia as a cited source

**Date:** 2026-06-15
**Status:** approved (design)
**Branch:** feat/component-equation-enforcement

## Problem

Tutor mode (`run_deep_tutor`) is **corpus-only**. Q&A, Extension, facilitate, and
resume already augment with Wikipedia via the shared `src/services/chat/research.py`
module, but the deep-tutor pipeline never calls it. Users want Wikipedia to count
as a valid, attributed source in tutor answers too.

## Decisions (locked)

| Question | Decision |
|---|---|
| **Surface** | Cited 🌐 source — clickable in the sources panel + inline citation badge. Full parity. |
| **Trigger** | Always, per extracted concept (≤3). Simple logic; concurrent with retrieval. |
| **Weight** | Augment-only. Corpus sources keep their ranks; Wikipedia is appended at trailing ranks. |

## Architecture

### Backend — `deep_tutor.py` / `run_deep_tutor`

1. **Fetch** (pure code, network): after concept extraction, fan out
   `research.wiki_evidence(concept, subject_id=concept)` for each concept via
   `asyncio.gather(..., return_exceptions=True)`, concurrent with corpus retrieval.
   Gated by env `TUTOR_DEEP_WIKI` (default `"1"`; `"0"` disables). Silent-degrade
   on any failure (research.py already swallows network errors → `[]`).

2. **Map** each wiki `Evidence` → a `Source`:
   - `book="wikipedia"` (sentinel), `book_name="Wikipedia"`
   - `chapter=""`, `section=<article title>`, `title=<article title>`
   - `excerpt=<summary>`, `chunk=<summary>`
   - `chunkId=f"wiki:{title}"`, `url=<article url>`
   - `score=0.0`, `rank=<len(corpus)+i+1>` (trailing)

3. **Append** wiki sources AFTER corpus sources. Corpus order/ranks are untouched
   → augment-only is true by construction (corpus always ranks first).

4. **Draft prompt**: the source bundle renders wiki rows with a `Wikipedia:` label.
   One instruction line: corpus is the authority; cite Wikipedia (by its index)
   only for breadth/definitions, never to override a textbook.

5. **Citation reconciliation**: a `TutorCitation` for a wiki source carries
   `url` + `book_name="Wikipedia"` so the frontend renders it as a 🌐 link.

### Schema (`schemas/_core.py`, `schemas/output.py`) — two optional fields

- `Source.url: str = ""`
- `TutorCitation.url: str = ""`

Both default-empty → backward compatible; legacy callers and stored rows unaffected.

### Frontend

- **Source panel row** + **citation badge card**: when `url` is non-empty, render a
  🌐 globe linking to the article (target=_blank) instead of the book-page link.
  Reuse the existing row/card component with one conditional branch.

### Lockstep artifacts (CLAUDE.md mandate)

- `web/src/data/tutorPipeline.ts` + `web/src/components/PipelineDiagram.tsx`:
  add a **"Wikipedia augment"** node parallel to retrieval (+ test).
- `docs/services/chat-features/36-deep-tutor.md`: mermaid graph + env table row
  (`TUTOR_DEEP_WIKI`).
- `docs/common ground/Elements/modes/tutor.html`: reflect the new node.
- `docs/system/invariants.md` + `docs/system/changelog.md`.

## Error handling

- Wikipedia fetch failure / timeout → `wiki_evidence` returns `[]` → answer is
  corpus-only, no error surfaced. The kill switch `TUTOR_DEEP_WIKI=0` fully bypasses.
- No new failure path can blank the turn (wiki is additive).

## Testing

Backend (`test_deep_tutor.py` / new `test_tutor_wiki.py`):
- wiki sources are appended after corpus sources (order + ranks preserved);
- `TUTOR_DEEP_WIKI=0` → no wiki fetch, no wiki sources;
- wiki fetch raising → degrades to corpus-only (no raise);
- a wiki `Source` maps with `url` set and `book="wikipedia"`.

Frontend (`MessageThread.test.tsx` / source-row test):
- a source/citation with `url` renders a 🌐 external link to the article.

## Out of scope (YAGNI)

- Gap-triggered fetching (chose always-on for simplicity).
- A `formula_cache`-style wiki cache.
- Per-section Wikipedia (only article summaries).
