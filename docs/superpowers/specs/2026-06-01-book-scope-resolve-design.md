# Book Scope Resolve + Clarify — Design Spec

**Date:** 2026-06-01
**Branch:** new branch off `main` at implementation time (e.g. `feat/book-scope-resolve`)
**Status:** approved design → ready for writing-plans

---

## 0 · Problem

A chapter-mode request like:

> "Help me with the chapter 7, sections 7.2 up to 7.4 of Hansen's introduction to probability."

fails to identify the book. Root cause: `agents/chapter.parse_scope` receives
**only book slugs** (`selected_books: ["islp", ...]`) and no metadata. The
parse-scope LLM therefore has nothing to match "Hansen's introduction to
probability" against, and falls open to `book_slug=""` unless exactly one book
is selected. On a miss it emits a flat "Chapter not found" with no common
ground.

## 1 · Goal

1. **Comprehension first.** Make the scope parser understand fuzzy, natural
   references — paraphrased titles, author-only ("Hansen"), typos, "chapter 7"
   → `ch07`, "sections 7.2 up to 7.4" → ordered section ids — by feeding it a
   compact **book catalog** (mechanism A, catalog-in-prompt).
2. **Confirm only in high necessity.** When the book/chapter is genuinely
   ambiguous or absent, return a **two-step common-ground** turn: a short chat
   line plus clickable candidate chips. A confident single match runs the flow
   immediately (no extra click).
3. **Applies to chapter modes (`facilitate`, `resume`) and `qa`.**

Out of scope: `tutor` (untouched); ingestion; new embeddings/indexes.

## 2 · Decisions (locked)

| Decision | Choice |
|---|---|
| Modes covered | `facilitate`, `resume`, `qa` |
| Confirm trigger | ambiguity / miss only (confident match auto-runs) |
| Confirm delivery | structured `clarify` SSE event: chat line + candidate chips |
| Match mechanism | **A — catalog-in-prompt** (one LLM call, no new infra) |
| Numeric section refs | folded in: "7.2 up to 7.4" → `["7.2","7.3","7.4"]` |

## 3 · Architecture

### 3.1 Book catalog — `src/services/chat/books.py`

New helper `parse_catalog() -> list[CatalogBook]` returning a compact record
per ingested book:

```python
class CatalogBook(BaseModel):
    slug: str
    name: str
    authors_short: str        # reuse existing _authors_short
    field: str
    chapters: list[str]       # ordered chapter ids, e.g. ["ch01","ch02",...]
```

- `name`, `authors_short`, `field` from the yaml registry (already loaded).
- `chapters` from `manifest.entries`, grouped by `book_slug`, sorted by
  `chapter_id`.
- Size: ~dozen books × a handful of fields → trivial token cost in a prompt.

### 3.2 Shared resolver — `src/services/chat/agents/_scope.py` (new)

Chinese-wall safe (chat sibling; imports only `src.core.*` +
`src.services.chat.*`). Used by both `chapter.py` and `qa.py`.

```python
class BookResolution(BaseModel):
    book_slug: str
    book_confidence: float            # 0..1, from the parse LLM
    book_candidates: list[str]        # candidate slugs, best-first
    chapter_id: str                   # normalised "chNN" or ""
    requested_subtopics: list[str]    # phrases + expanded numeric refs

async def resolve_book(
    message: str,
    *,
    selected_slugs: list[str] | None,
    catalog: list[CatalogBook],
    model: str | None = None,
) -> BookResolution: ...
```

- Injects the catalog into the parse-scope system/user prompt.
- LLM returns `book_slug`, `book_confidence`, `book_candidates`, `chapter_id`,
  `requested_subtopics`.
- **Deterministic post-step:** numeric refs (e.g. `"7.2"`) are NOT left to the
  LLM closest-match — they are matched downstream to `h2_path` by
  section-number prefix in `resolve_subtopics`. Word phrases keep the existing
  semantic closest-match.
- **Fail-open** preserved: any parse error → single-selected-book slug, empty
  chapter/subtopics, `book_confidence=1.0` if exactly one book selected (so a
  single-book session never sees a clarify).

`parse_scope` in `chapter.py` is refactored to delegate to `resolve_book`
(keeping its `ChapterScope` return by mapping fields), so existing chapter tests
keep their seam.

### 3.3 Confirm gate

In `run_chapter` and `run_qa`, after resolve, fire **clarify** only when:

- `book_slug == ""`, or
- `book_confidence < BOOK_CONFIRM_CUTOFF` (default `0.6`), or
- `len(book_candidates) >= 2` within a close margin (true ambiguity), or
- `chapter_id` named but not in the chosen book's `chapters[]`, or
- named sections resolve to **zero** sections.

Else → run the flow immediately. Internal threshold; **not** a user-facing knob
(semantics = "ambiguity/miss"). `CHAPTER_CLARIFY=0` kill-switch reverts to the
old fail-open behaviour.

### 3.4 SSE — new `clarify` event

Terminal for the turn (followed by `done`; no `structured_output`):

```jsonc
{
  "type": "clarify",
  "reason": "book_ambiguous" | "book_unknown" | "chapter_missing" | "sections_empty",
  "message": "I don't have a book by Hansen. Did you mean one of these?",  // chat line, markdown
  "candidates": [
    {"slug": "islp", "name": "An Introduction to Statistical Learning",
     "authors_short": "James et al.", "chapters": ["ch01","ch02","..."]}
  ],
  "chapter_guess": "ch07",            // "" if none
  "sections_guess": ["7.2","7.3","7.4"]
}
```

Event order on a clarify turn:
```
meta → stage(parse) → clarify → done
```
`ChatRequest` is unchanged. Stage keys remain `parse/resolve/map/stitch/ground`.

## 4 · Frontend

### 4.1 `web/src/components/ClarifyCard.tsx` (new)

Renders on a `clarify` event:

- `message` line (markdown).
- Candidate **book chips** (`name` · `authors_short`). Click → set the book in
  the store selection.
- If `chapter_guess` / `sections_guess` present → a chapter+sections chip that
  prefills the existing chapter picker state.
- Clicking a chip resolves scope (book selected + chapter/sections prefilled)
  and **re-sends** the original turn. Plain re-typing also works.

### 4.2 SSE consumer (`web/src/.../store.ts` stream handler)

Add a `clarify` case → push a `ClarifyCard` message and end the turn (parallel
to how `structured_output` is handled).

### 4.3 Pipeline diagrams (lockstep)

- `ChapterPipelineDiagram.tsx` + `data/chapterMode.ts`: relabel the parse node
  **"parse + resolve scope"**; add a branch edge to a terminal **"clarify
  (if ambiguous)"** node.
- `QAPipelineDiagram` + `data/qaMode.ts`: same resolve/clarify annotation on the
  entry node.
- After the change, open the (i) modals on **:5175** and confirm they match
  `docs/common ground/Elements/index.html`.

## 5 · Lockstep artifacts (CLAUDE.md rule)

| Aspect | Where |
|---|---|
| Backend logic | `agents/_scope.py` (new), `agents/chapter.py`, `agents/qa.py`, `books.py` |
| Prompts | `prompts/chapter.py` (`CHAPTER_PARSE_PROMPT` → catalog-aware) |
| Schemas | `schemas/output.py` (`CatalogBook`, `BookResolution`), `__init__.py` re-export; clarify event is SSE-only (no request change) |
| Env flags | `BOOK_CONFIRM_CUTOFF=0.6`, `CHAPTER_CLARIFY=1` |
| Modal cards | `ChapterPipelineDiagram.tsx` + `chapterMode.ts`; `QAPipelineDiagram` + `qaMode.ts`; new `ClarifyCard.tsx` |
| Backend mermaid | `docs/services/chat-features/52-book-scope-resolve.md` (new) |
| Per-feature doc | `52-book-scope-resolve.md`; update `51-qa-mode.md` |
| SSE doc | `docs/services/chat.md` (new `clarify` event) |
| Reference graph | `docs/common ground/Elements/index.html` — Chat page |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| Tests | backend `test_scope.py` + chapter/qa gate tests; frontend `ClarifyCard.test.tsx`, diagram tests |

## 6 · Tests

**Backend** (monkeypatch the `_chat` seam):
- `resolve_book`: "Hansen's introduction to probability" → best candidate slug;
  "chapter 7" → `ch07`; "sections 7.2 up to 7.4" → `["7.2","7.3","7.4"]`.
- Confirm gate fires on: unknown book, ≥2 close candidates, chapter not in
  `chapters[]`, sections resolve to zero.
- Confirm gate does **not** fire on a confident single match (flow runs).
- `clarify` event shape (reason, candidates, guesses).
- Single-book session never clarifies (fail-open confidence 1.0).

**Frontend:**
- `ClarifyCard.test.tsx`: chips render; click sets book + prefilled
  chapter/sections; re-send fires.
- Diagram tests: chapter + qa diagrams include the new resolve/clarify nodes.

## 7 · Env flags

| Var | Default | Effect |
|---|---|---|
| `BOOK_CONFIRM_CUTOFF` | `0.6` | min `book_confidence` to auto-run without clarify |
| `CHAPTER_CLARIFY` | `1` | `0` → kill-switch, old fail-open (no clarify event) |

## 8 · Definition of done

- Fuzzy NL request resolves to the right book/chapter/sections without exact
  titles.
- Ambiguous/missing book → clarify card with chips + chat line; click runs the
  flow.
- Confident match → flow runs with no extra step.
- Chapter + QA diagrams and the (i) modals updated and verified on :5175 against
  `Elements/index.html`.
- Docs (feature 52, qa 51, chat.md, invariants, changelog) updated.
- All backend + frontend tests green; prod build green.
