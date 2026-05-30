# 42 — Author-perspective diversity (tutor retrieval)

## Why

Tutor answers tended to pull every source from the single most-relevant book,
so a learner never saw how a different author frames the same idea. This step
forces the section selection to span multiple authors when the corpus supports
it, enabling synthesis / comparison across perspectives.

## Facet

Author primary, **year** as tiebreak:
- author identity = `authors_short` → `authors` → `book` (first non-empty,
  normalized lower/stripped) via `diversity.author_key()`.
- when picking a 2nd+ section from the same author, prefer a different `year`
  (classic vs modern treatment).

## Flow

```
density_select (relevance ranking by concept-density × similarity)
        │  scored section keys (book_slug, section_id) + per-key author/year/score
        ▼
diversify_section_keys(target_authors, top_sections)      ← Plan A
        │  round-robin across distinct authors, year tiebreak
        ▼
stratified fill if distinct_authors < target              ← Plan B
        │  best sections for under-represented authors (from wide pool)
        ▼
expand sections → cross-encoder rerank → draft
```

## Adaptive count (Auto)

The count is a **cap**, not a fixed quota. Effective target:

```
min( cap , model_suggestion , authors_available_in_pool )
```

- `authors_available_in_pool` — round-robin saturation; single-author topic → 1.
- `model_suggestion` — in **Auto** mode the concept-extraction call also returns
  a `perspectives` integer (1..cap) judging how comparative/broad the *question*
  is. Folded into the existing call via `extract_concepts_ex` +
  `EXTRACT_CONCEPTS_BUDGET_PROMPT` — **no extra LLM call**. The reasoning model =
  whatever is selected for the Concept-extraction node.
- `cap` — your ceiling (`TUTOR_DIVERSITY_MAX_AUTHORS`, default 4).

Diversity is **additive**: it never suppresses naturally-relevant diverse
sources, only stops padding spread beyond the target.

## Config

| Knob | Where | Default | Meaning |
|---|---|---|---|
| `diversityAuthors` | request field | `null` | `"auto"` = model decides (≤cap, ≤available); `0`/`1` = off; `N≥2` = hard cap; `null` = env default. |
| `TUTOR_DIVERSITY` | env | `1` | Master on/off. |
| `TUTOR_DIVERSITY_DEFAULT` | env | `auto` | Mode when request omits the field. |
| `TUTOR_DIVERSITY_MAX_AUTHORS` | env | `4` | Cap / Auto ceiling. |
| `TUTOR_DIVERSITY_TARGET_AUTHORS` | env | `3` | Legacy cap fallback. |

UI: **Author diversity** node in the About-model pipeline diagram
(`tutorPipeline.ts` id `diversity`), a `NodeChoiceDropdown` with
**Off / Auto / 2 / 3 / 4** (`SET` badge), default **Auto**. Value type
`ChoiceValue = number | "auto"`. Selection flows `App.diversityAuthors` →
`useChat` → POST body.

## Code

- `src/services/chat/retrievers/diversity.py` — `author_key`, `AuthorMeta`,
  `diversify_section_keys`, `build_author_filter_from_candidates`.
- `src/services/chat/agents/deep_tutor.py` — `_density_select(target_authors=)`,
  resolution in `run_deep_tutor`.
- Frontend — `web/src/components/NodeChoiceDropdown.tsx`, `PipelineDiagram.tsx`,
  `tutorPipeline.ts` (`rerank → diversity → image_judge`).

## Tests

`src/services/chat/tests/test_diversity.py` — 23 cases (round-robin interleave,
target<2 passthrough, saturation, year tiebreak, filter helper).

## Section-parent (topic) diversity — secondary tiebreak (Phase 2, 2026-05-30)

After the author floor, `_density_select` applies a secondary **chapter-diversity
pass** via `_apply_section_parent_diversity`:

- If all surviving sources share the same `chapter` field (same parent framing),
  the best dropped source from a **different chapter** is reinserted (at most one
  extra slot).
- Author-diversity is **primary** (unchanged); chapter spread is the secondary
  tiebreak to prevent MSE-chapter tunnel-vision when the corpus has alternative
  framings (e.g. a regularization chapter that also covers bias-variance).
- Degrades gracefully when `chapter` metadata is absent (returns sources unchanged).
- No new LLM call; no new I/O.

## Known limitation / next step

Plan B (stratified fill) currently draws only from the already-fetched wide
candidate pool, so a genuinely single-author pool cannot be diversified. True
stratified retrieval: map under-covered authors → their `book_slug`s
(`books.list_books`) → `hybrid_search(book_slugs=...)` to pull their best
sections directly from Qdrant. The book-slug payload filter already exists
(`retrieval._build_filter`).

A complementary improvement: nudge the draft prompt to explicitly *compare /
synthesize* across the now-diverse sources (currently the prompt is
perspective-agnostic).
