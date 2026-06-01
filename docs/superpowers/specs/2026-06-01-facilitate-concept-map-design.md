# Facilitate Concept-Map Mode — Design Spec

**Date:** 2026-06-01
**Branch:** new branch off `feat/nontutor-mode-modals` at implementation time (e.g. `feat/facilitate-concept-map`)
**Status:** approved design → ready for writing-plans
**Hindsight digest:** `docs/superpowers/hindsight/2026-06-01-facilitate-concept-map-options.md`

---

## 0 · Problem

The current `facilitate` mode **expands** each section into a long essay (per-section
map prompt, ~250–400 tok narrative). The result makes the subject *harder*, not
easier: it lengthens instead of clarifying, never surfaces the section's key
points, and silently glosses over concepts the section only *references* (e.g.
"strong assumption of normality") without explaining them.

## 1 · Goal

Re-architect `facilitate` so it **teaches by clarifying, not expanding**:

1. An agent builds a **concept map** of each section — its key concepts,
   theorems, formulas, and the flow between them.
2. Each section is rendered as **simpler language + the top key points** (filtered,
   tight), not a longer essay.
3. Concepts the section only *references* (not defined in-section) are
   **re-queried in the RAG** to fetch a short explanation, with author/section
   preference (below). Concepts become **clickable colored anchors**; clicking
   opens a modal explaining that concept; on markdown export the explanation
   becomes a **footnote**.

Out of scope: `resume`, `qa`, `tutor` (unchanged). No ingestion changes.

## 2 · Decisions (locked)

| Decision | Choice |
|---|---|
| Agent structure | **Concept-map-first, two-pass** (Plan-and-Solve ch.5 + four-node RAG ch.4) |
| Mode coverage | `facilitate` only; `resume`/`qa`/`tutor` untouched |
| Body shape | simplify + **top 3–6 key points** per section; NOT expansion |
| Concepts/section cap | ~3–5 anchors by teaching importance |
| Sub-retrieval trigger | only `referenced-only` concepts (explained-in-section ones get their blurb free from section text) |
| Retrievals/concept | 1 (capped) |
| Adaptive policy | ① same author, nearest prior section (formal-statement preference) → ② same author anywhere in book → ③ other authors (cross-book) — escalate only when score stays below threshold |
| Anchor UI | colored clickable button → modal (explanation + provenance); markdown export → footnote |
| Prompts | one short single-purpose prompt per node (avoid the long-prompt adherence trap) |
| Validation | offline LLM-as-judge eval harness; pick best variant; then ship as default |

## 3 · Architecture

New pipeline for `facilitate` (replaces its current `map`/`stitch`). `resume`
keeps the existing `run_chapter` path unchanged.

```
parse+resolve scope → ordered-fetch → [per section, in order]
    concept-map  →  for each referenced concept: adaptive sub-retrieval
                 →  simplify+keypoints teach (with resolved concepts)
    → verify(grounding) → assemble FacilitateDigest
```

Mermaid (for the feature doc + modal):
```mermaid
flowchart LR
  Q[user msg] --> P[parse + resolve scope]
  P --> F[fetch chapter (ordered)]
  F --> M[concept-map per section]
  M -->|referenced concepts| R[adaptive sub-retrieval\nsame-author → prior → fallback]
  M -->|explained concepts| T
  R --> T[simplify + key points\n(+ concept anchors)]
  T --> V[verify grounding]
  V --> D[FacilitateDigest]
```

### 3.1 Node contracts

| Node | Input | Output | Model | Fail-open |
|---|---|---|---|---|
| **concept-map** | section text + h2_path | `SectionMap{key_points[], concepts[]}` where each concept = `{term, kind, status: explained\|referenced, in_section_gloss?}` | nano (typed JSON) | parse fail → empty concepts, key_points = first sentences |
| **sub-retrieval** | each `referenced` term + book_slug + current section_id | best supporting chunk + provenance | embeddings + rerank (no LLM for fetch) | no acceptable hit → concept kept, `explanation` from in-section context, `provenance.fallback=true` |
| **explain-concept** | retrieved chunk + term | 1–3 sentence plain explanation | nano | error → use chunk synopsis |
| **teach (simplify+keypoints)** | section text + key_points + resolved concepts | `body` (markdown, simpler language, top key points, inline `[[cN]]` anchors) | section's configured model (`stageModels["teach"]` → env → qwen-plus) | error → render key_points as bullets |
| **verify** | body + section + concept explanations | `grounding{ok, unsupported[], confidence}` | nano | error → ok=false, low conf; never blocks |

Order-preservation invariant preserved: sections walked in `section_id` order;
block order == section order.

### 3.2 Adaptive sub-retrieval policy (the heart)

For a `referenced` concept term in section `S` of book `B` (author `A`):

1. **Same author, prior sections** — hybrid query for `term` scoped to `book_slug=B`,
   keep only candidates with `section_id < S.section_id`, **boost** chunks whose
   text matches a formal-statement cue (`Definition`, `Theorem`, `Assumption`,
   `Lemma`, `Proposition`). Take top-1 after rerank if score ≥ `CONCEPT_MIN_SCORE`.
2. **Same author, whole book** — drop the prior-section filter; same book. Take
   top-1 if score ≥ threshold.
3. **Other authors** — cross-book hybrid (same field collections), top-1 if score
   ≥ threshold.
4. **None** — keep the concept anchor but mark `provenance.fallback=true`; the
   explanation falls back to the in-section gloss; UI shows "from this section".

New retrieval helper in `src/services/chat/retrieval.py`:
`fetch_concept_support(term, *, book_slug, before_section_id, formal_pref=True, min_score=...) -> ConceptSupport | None`
— wraps `hybrid_search` (rerank on) + a payload/post filter for the author/section
preference + the formal-statement boost. Chinese-wall safe (chat sibling).

## 4 · Schemas (`src/services/chat/schemas/output.py`)

```python
class ConceptProvenance(BaseModel):
    book_slug: str = ""
    book_name: str = ""
    authors_short: str = ""
    section: str = ""           # h2_path of the support chunk
    page_from: int = -1
    page_to: int = -1
    chunk_id: str = ""
    same_author: bool = True    # False when policy escalated to other authors
    fallback: bool = False      # True = no acceptable retrieval; in-section gloss

class ConceptAnchor(BaseModel):
    id: str                     # "c1", "c2", … (referenced inline as [[c1]])
    term: str
    kind: Literal["concept", "theorem", "formula"] = "concept"
    explanation: str            # 1–3 sentence plain-language explanation
    provenance: ConceptProvenance

class FacilitateBlock(BaseModel):
    h2_path: str
    section_id: str
    key_points: list[str] = Field(default_factory=list)   # the filtered top points
    body: str                   # simpler-language teaching, inline [[cN]] anchors
    concepts: list[ConceptAnchor] = Field(default_factory=list)
    page_from: int = -1
    page_to: int = -1

class FacilitateDigest(BaseModel):
    mode: Literal["facilitate"]
    scope: ChapterScope         # REUSE (book/chapter/sections + resolution)
    intro: str = ""
    blocks: list[FacilitateBlock]
    outro: str = ""
    math_blocks: list[str] = Field(default_factory=list)
    grounding: dict = Field(default_factory=dict)
```

- `[[cN]]` markers in `body` reference `block.concepts[].id`. (Distinct from the
  existing `[n]` citation markers, which stay for source citations.)
- `resume` keeps emitting `ChapterDigest`; `facilitate` now emits
  `FacilitateDigest` (new `structured_output.schema = "FacilitateDigest"`).
- Re-export the new models from `schemas/__init__.py`.

## 5 · SSE contract

Reuses the event sequence; facilitate stage events become:
```
meta → stage(parse) → [clarify branch unchanged] → stage(fetch) →
stage(map:<h2>) → stage(retrieve:<term>)… → stage(teach:<h2>) (one set per section, in order) →
stage(verify) →
structured_output{schema:"FacilitateDigest", data} → sources_full → usage → done
```
- New `structured_output.schema` value `"FacilitateDigest"`; unknown schemas
  already fall back gracefully on the frontend.
- Per-section `stage` events carry `h2_path`/`term` so the thread animates.

## 6 · Frontend

- **`web/src/types.ts`**: add `ConceptProvenance`, `ConceptAnchor`,
  `FacilitateBlock`, `FacilitateDigest`; add the `schema:"FacilitateDigest"`
  variant to `StructuredOutputEvent`.
- **`web/src/components/FacilitateDigestCard.tsx`** (new): renders intro, then per
  block: the `key_points` (a compact "Key points" list), then `body` with inline
  concept anchors. Each `[[cN]]` renders as a **colored pill button**
  (`.concept-anchor`, kind-tinted). Reuses the chapter-card stylesheet family
  (`chapter.css`) — add `.concept-anchor*` rules.
- **`web/src/components/ConceptModal.tsx`** (new): on anchor click, modal shows
  `term`, `kind` tag, `explanation`, and provenance line (`author · section · p.`,
  with a "from this section" note when `fallback`, and a "other author" note when
  `!same_author`). Dismiss on overlay/Esc.
- **`MessageThread.tsx`**: render `FacilitateDigestCard` when
  `structuredOutput.schema === "FacilitateDigest"` (alongside ChapterDigest).
- **Markdown export** (`web/src/lib/exportMarkdown.ts`): each concept anchor →
  inline footnote ref `[^cN]`; append a footnotes section per block/digest with
  `[^cN]: <term> — <explanation> (<provenance>)`.

## 7 · Models & prompts

Default models: map=nano, explain-concept=nano, teach=`stageModels["teach"]`→env→qwen-plus,
verify=nano. **Each prompt is short and single-purpose** (`prompts/chapter.py`,
new constants): `FACILITATE_MAP_PROMPT`, `FACILITATE_EXPLAIN_PROMPT`,
`FACILITATE_TEACH_PROMPT`, `FACILITATE_VERIFY_PROMPT`. The old
`CHAPTER_MAP_FACILITATE_PROMPT` is removed from the facilitate path (resume keeps
`CHAPTER_MAP_RESUME_PROMPT`).

Prompt intents (final wording chosen by the eval harness, §9):
- **map**: "List the section's 3–6 key points and its key concepts/theorems/formulas.
  For each concept mark whether it is *defined here* or only *referenced*. Return JSON."
- **explain-concept**: "In 1–3 plain sentences, explain <term> using ONLY the provided
  passage. No padding."
- **teach**: "Rewrite this section for a learner: simpler language, keep ONLY the key
  points, do not lengthen. Insert [[cN]] where each listed concept first appears.
  Return markdown."
- **verify**: grounding check (reuse existing ground contract).

## 8 · Stage keys / env / knobs

- `stageModels` keys for facilitate: `"map"`, `"explain"`, `"teach"`, `"verify"`.
- Env: `FACILITATE_MAX_CONCEPTS` (default 5), `FACILITATE_MAX_KEYPOINTS` (6),
  `CONCEPT_MIN_SCORE` (default 0.30), `FACILITATE_SUBRETRIEVAL` (1 = on; 0 =
  anchors from in-section gloss only), `CHAPTER_GROUND` (reuse).
- No new `ChatRequest` fields.

## 9 · Validation — offline eval harness (the "keep testing" loop)

A pytest-driven harness `src/services/chat/eval/facilitate_eval.py` (+ marker
`-m facilitate_eval`, not in default CI run):

- **Fixture**: hansen ch07 §7.1–7.4 (the live failing example) — sections fetched
  once and cached.
- **Variants**: 2–3 prompt/structure variants (e.g. map+teach merged vs split;
  key-points-as-bullets vs prose; with/without formal-statement boost).
- **Scorer**: multi-dimensional **LLM-as-judge** (rubric from ch.8) scoring each
  variant 1–5 on: **clarity**, **faithfulness/grounding**, **key-point coverage**,
  **non-expansion** (penalize length > source), **concept-identification quality**
  (did it flag the right referenced concepts, e.g. "strong assumption of
  normality"?). 3 runs/variant → mean + variance (per the draft-model variance
  lesson).
- **Output**: a ranked table written to `docs/superpowers/eval/2026-06-01-facilitate-variants.md`.
- The **winning variant's prompts** become the shipped defaults in
  `prompts/chapter.py`. The harness stays in-repo for future tuning.

This harness runs DURING implementation (before finalizing prompts), not in prod.

## 10 · Lockstep artifacts (CLAUDE.md rule)

| Aspect | Where |
|---|---|
| Backend logic | new `src/services/chat/agents/facilitate.py` (facilitate splits out of `chapter.py`; `chapter.py` keeps `resume`); `retrieval.py` (`fetch_concept_support`); dispatch in `router.py` routes `facilitate`→`run_facilitate`, `resume`→`run_chapter` |
| Prompts | `prompts/chapter.py` (4 new FACILITATE_* constants) |
| Schemas | `schemas/output.py` (+ `__init__` re-export) |
| Env flags | §8 vars + env table in feature doc |
| Modal card (graph) | `web/src/data/chapterPipeline.ts` (facilitate variant nodes: map/retrieve/teach/verify) + `ChapterPipelineDiagram.tsx`; `chapterMode.ts` copy |
| Backend mermaid | new `docs/services/chat-features/53-facilitate-concept-map.md` |
| Per-feature doc | new `53-facilitate-concept-map.md`; add it to the feature-doc index list in `CLAUDE.md` "Where to look" row |
| Reference graph | `docs/common ground/Elements/chat.html` |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| Tests | `agents` tests + `FacilitateDigestCard.test.tsx` + `ConceptModal.test.tsx` + diagram test + eval harness |

## 11 · Tests

**Backend** (monkeypatch `_chat` + `hybrid_search`):
- concept-map parses key_points + concepts with status flags; cap enforced.
- `fetch_concept_support`: same-author-prior preferred; escalates on low score;
  returns None → fallback path.
- referenced concept triggers retrieval; explained concept does NOT.
- teach inserts `[[cN]]` anchors matching `concepts[].id`; order preserved.
- FacilitateDigest assembled; verify never blocks; fail-open paths.
- SSE emits `structured_output.schema=="FacilitateDigest"`.

**Frontend:**
- `FacilitateDigestCard.test.tsx`: key points render; `[[cN]]` → clickable pill.
- `ConceptModal.test.tsx`: click opens modal with explanation + provenance;
  fallback/other-author notes.
- export: anchors → `[^cN]` footnotes.
- diagram test: facilitate diagram includes map/retrieve/teach/verify.

**Eval:** the §9 harness (manual/marked run).

## 12 · Definition of done

- Facilitate output is **shorter/clearer** than before, lists key points, and
  flags referenced concepts as clickable anchors backed by adaptive
  same-author-first retrieval (verified on hansen ch07 §7.1–7.4).
- Clicking an anchor opens a modal; markdown export renders footnotes.
- Eval harness ran; winning prompts shipped; ranked table committed.
- resume/qa/tutor unchanged; diagrams + (i) modal + docs updated and
  browser-verified on :5175.
- All backend + frontend tests green; prod build green.
