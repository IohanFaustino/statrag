# Feature 53 — Facilitate concept-map mode (clarify-not-expand redesign)

**Branch:** `feat/facilitate-concept-map`
**Date:** 2026-06-01
**Spec:** [`docs/superpowers/specs/2026-06-01-facilitate-concept-map-design.md`](../../superpowers/specs/2026-06-01-facilitate-concept-map-design.md)
**Hindsight:** [`docs/superpowers/hindsight/2026-06-01-facilitate-concept-map-options.md`](../../superpowers/hindsight/2026-06-01-facilitate-concept-map-options.md)
**Eval ranked table:** [`docs/superpowers/eval/2026-06-01-facilitate-variants.md`](../../superpowers/eval/2026-06-01-facilitate-variants.md)

---

## Purpose — clarify, not expand

The original `facilitate` mode taught by *expanding* each section — generating additional prose beyond what the source text said. This produced answers that were longer than the source itself, mixed author voice with LLM confabulation, and buried the key structural relationships of a chapter under extra narrative.

The redesign inverts the goal: **facilitate now teaches by clarifying**, not expanding. The body of each block must be *shorter* than its source section. Extra detail is offloaded to **concept anchors** — modal pop-ups that open inline on click. Step-bearing formulas get a dedicated **formula anchor** whose modal renders the derivation in KaTeX. The section structure is therefore:

- Short paragraphs (body stays lean).
- Bullet key-points per concept.
- `[[cN]]` anchors in the text that open a `ConceptModal` with the full concept provenance + supporting quotes.
- Formula anchors — `[[cN]]` markers with `kind="formula"` — that show derivations inline via KaTeX.
- Export flattens anchors to footnotes.

This approach keeps the main reading flow readable for a student who already has the book open, and makes depth-on-demand rather than depth-by-default the interaction model.

---

## Pipeline

```
parse + resolve scope
        │
        ▼
   fetch (ordered) ← chapter sections in page_from order
        │
        ▼ ── for each section ──────────────────────────────────────
   [map]  concept-map node
          • extracts key points
          • flags each concept: "explained" (inline) or "referenced" (needs sub-retrieval)
        │
        ├─ "explained" concepts ────────────────────┐
        │                                            │
        ▼                                            │
   [retrieve]  adaptive sub-retrieval               │
          • fetch_concept_support per concept        │
          • escalating author/section policy         │
        │                                            │
        └────────────────────────────────────────────┤
                                                     ▼
   [teach]  simplify + key-points
          • short paragraphs
          • [[cN]] anchors (concept; kind="formula" for formulas)
          • prior_context threaded forward
        │
        ▼
   [verify]  grounding verdict (advisory)
        │
        ▼
   FacilitateDigest  ──► SSE structured_output
```

### Mermaid

```mermaid
flowchart TD
  U[user message] --> PR[parse + resolve scope]
  PR --> FE[fetch — ordered sections page_from]
  FE --> MAP[map — concept-map + key points]
  MAP -->|explained concepts| TCH[teach — simplify + [[cN]] anchors (kind=concept/formula)]
  MAP -->|referenced concepts| RTV[retrieve — adaptive sub-retrieval]
  RTV --> TCH
  TCH --> VRF[verify — grounding verdict]
  VRF --> FD[FacilitateDigest]
  style MAP fill:#1a1e2a,stroke:#4D6BFE,color:#fff
  style RTV fill:#1f2a1a,stroke:#3fb950,color:#fff
  style VRF fill:#3a1d1f,stroke:#E5484D,color:#fff
```

---

## Adaptive sub-retrieval — `retrieval.fetch_concept_support`

For every concept flagged `"referenced"` by the map node, the pipeline calls `fetch_concept_support(concept, book_slug, section_id)` with an **escalating policy**:

| Priority | Strategy | Condition to escalate |
|---|---|---|
| 1 | Same author + nearest **prior** section (formal-statement boost) | score < `CONCEPT_MIN_SCORE` |
| 2 | Same author anywhere in the book | score < `CONCEPT_MIN_SCORE` |
| 3 | Other authors (cross-book) | — (terminal) |

The prior-section preference surfaces the definition or theorem that the current section builds on. The formal-statement boost up-weights payloads that contain a numbered statement (`Definition X.Y`, `Theorem`, `Proposition`). Cross-author retrieval only fires when the same author has no adequate coverage (score < `CONCEPT_MIN_SCORE`, default `0.30`).

The result is a `ConceptProvenance` record attached to the `ConceptAnchor` for that concept.

---

## Schemas

Defined in `src/services/chat/schemas/output.py`.

```python
class ConceptProvenance(BaseModel):
    concept: str
    source_section_id: str
    source_book_slug: str
    authors_short: str
    quote: str          # verbatim supporting text
    score: float        # retrieval score

class ConceptAnchor(BaseModel):
    id: str             # "c1", "c2", … / "f1", "f2", … for formulas
    label: str          # display text for the anchor
    kind: Literal["concept", "formula"]
    provenance: list[ConceptProvenance]
    derivation: str     # KaTeX string (non-empty for formula anchors)

class FacilitateBlock(BaseModel):
    section_id: str
    h2_path: str
    page_from: int
    page_to: int
    body: str           # short paragraphs; [[cN]] inline (kind="formula" for formula anchors)
    key_points: list[str]
    anchors: list[ConceptAnchor]
    citations: list[TutorCitation]

class FacilitateDigest(BaseModel):
    mode: Literal["facilitate"]
    scope: ChapterScope
    blocks: list[FacilitateBlock]   # chapter reading order, never re-sorted
    citations: list[TutorCitation]  # global flattened list
    math_blocks: list[str]
    grounding: dict
```

`FacilitateDigest` is the `structured_output.schema` value emitted on every `facilitate` turn. `resume` is unchanged — it still uses `run_chapter` / `ChapterDigest`.

---

## Concept anchor / modal / footnote UX

### Inline anchors

The teach node embeds `[[cN]]` markers in the body text wherever a concept is first meaningfully used. Formula anchors also use the `[[cN]]` marker (with `kind="formula"`) and appear at the step in a derivation where the formula is introduced. The renderer replaces each marker with a clickable badge.

### ConceptModal

Clicking a `[[cN]]` badge opens `ConceptModal` (React component):

- Header: concept label.
- Provenance cards: supporting quotes from `ConceptAnchor.provenance`, with author / section / page attribution.
- For formula anchors (`[[cN]]` with `kind="formula"`): a KaTeX block rendering `derivation`.

### Export to footnotes

When the user exports a conversation to Markdown (zip export), `exportMarkdown.ts` replaces `[[cN]]` markers with `[^cN]` footnotes. Each footnote lists the concept label + first provenance quote. Formula anchors become a display-math block in the footnote. No anchor modal state is preserved (Markdown is inherently flat); the export is still readable offline.

### Readability rules

The teach node is prompted with explicit readability constraints:

1. Body paragraphs: ≤ 3 sentences each.
2. Key points: ≤ `FACILITATE_MAX_KEYPOINTS` (default 6) bullets per section.
3. Concepts: ≤ `FACILITATE_MAX_CONCEPTS` (default 5) anchors per section. Extra concepts are folded into body prose without an anchor.
4. The body MUST be shorter than the source section. Any block that exceeds the source token count is a teach-node failure (prompt violation).
5. Prior context is threaded forward: each block's teach call receives a `prior_context` summary of already-covered concepts so the model avoids re-explaining.

---

## SSE stage keys

`facilitate` emits `structured_output{schema:"FacilitateDigest"}`. The stage progress events use the following keys in the SSE `stage` field:

| Stage key | Description |
|---|---|
| `map` | Concept-map extraction running (per section) |
| `retrieve` | Adaptive sub-retrieval running (per referenced concept) |
| `teach` | Simplify + anchor generation running (per section) |
| `verify` | Grounding verdict running |

`stageModels` overrides use the same keys: `map`, `retrieve` (no LLM, ignored), `teach`, `verify`. The `retrieve` stage key is present in the progress event sequence for observability but does not accept a model override (retrieval is embedding-only).

---

## Env flags

| Var | Default | Effect |
|---|---|---|
| `FACILITATE_MAX_CONCEPTS` | `5` | Max `[[cN]]` anchors emitted per section |
| `FACILITATE_MAX_KEYPOINTS` | `6` | Max bullet key-points per section block |
| `CONCEPT_MIN_SCORE` | `0.30` | Retrieval score threshold for sub-retrieval escalation |
| `FACILITATE_SUBRETRIEVAL` | `1` | `0` = disable adaptive sub-retrieval; all concepts inlined |
| `FACILITATE_<STAGE>_MODEL` | nano (all stages) | Per-stage model override (`MAP`/`EXPLAIN`/`TEACH`/`VERIFY`). All default to `gpt-5.4-nano-2026-03-17`. **Teach moved off `qwen-plus` → nano on 2026-06-03** after the model sweep (nano beat qwen on quality *and* cost; qwen ran away to ~67k out-tok/85s per teach call). See [`docs/superpowers/eval/2026-06-03-facilitate-reasoning-models.md`](../../superpowers/eval/2026-06-03-facilitate-reasoning-models.md). |
| `CHAPTER_CLARIFY` | `1` (shared) | Kill-switch for book-scope clarify gate (feature 52) |
| `CHAPTER_GROUND` | `1` (shared) | `0` = skip grounding-verify node |

---

## Frontend

| Component / file | Path | Role |
|---|---|---|
| `FacilitateDigestCard` | `web/src/components/FacilitateDigestCard.tsx` | Top-level renderer for `FacilitateDigest`; iterates `blocks` in order |
| `ConceptModal` | `web/src/components/ConceptModal.tsx` | Modal opened by `[[cN]]` badge clicks (concept or formula kind); shows provenance + KaTeX |
| `FACILITATE_PIPELINE` | `web/src/data/facilitatePipeline.ts` | Static pipeline node/edge definitions (map/retrieve/teach/verify) |
| `MessageThread` | `web/src/components/MessageThread.tsx` | Render branch on `schema === "FacilitateDigest"` → `<FacilitateDigestCard>` |
| Facilitate `(i)` modal | `web/src/components/ChapterFacilitateModal.tsx` | Pipeline diagram showing map/retrieve/teach/verify nodes with per-stage model pickers |

The `(i)` modal pipeline diagram (`FACILITATE_PIPELINE`) shows four stages: **map** (concept-map extraction), **retrieve** (adaptive sub-retrieval, data-only badge), **teach** (simplify + anchors), **verify** (grounding). The retrieve stage is shown as a data node (no model picker) because it is embedding-only.

---

## Eval harness

**Location:** `src/services/chat/eval/facilitate_eval.py`

An LLM-judge harness (`-m facilitate_eval`) that scores `FacilitateDigest` outputs on:

- **Brevity ratio**: block body tokens / source section tokens (target < 1.0).
- **Anchor quality**: does each `ConceptAnchor.provenance` quote actually support the anchor label?
- **Key-point completeness**: do key-points cover the most important claims in the section?
- **Grounding**: are inline citations accurate?

The judge uses a nano model and outputs a per-block score table plus a summary row. Results for the initial variant comparison are in the ranked table at [`docs/superpowers/eval/2026-06-01-facilitate-variants.md`](../../superpowers/eval/2026-06-01-facilitate-variants.md).

---

## Resume is unchanged

`resume` mode continues to use `run_chapter` / `ChapterDigest` (dense per-section summaries, no concept anchors). The redesign is specific to `facilitate`.

---

## Synced-artifacts checklist

A logic change to the facilitate concept-map pipeline is incomplete until **all** of these reflect it:

| Aspect | Path |
|---|---|
| Agent logic | `src/services/chat/agents/facilitate.py` |
| Adaptive sub-retrieval | `src/services/retrieval/fetch_concept_support` (or equivalent in `facilitate.py`) |
| Prompts | `src/services/chat/prompts/facilitate.py` |
| Output schemas | `src/services/chat/schemas/output.py` (`ConceptProvenance`, `ConceptAnchor`, `FacilitateBlock`, `FacilitateDigest`) |
| Mode registration | `src/services/chat/modes.py` |
| Frontend types | `web/src/types.ts` |
| Renderer | `web/src/components/FacilitateDigestCard.tsx` + `MessageThread.tsx` wiring |
| Concept modal | `web/src/components/ConceptModal.tsx` |
| Pipeline data | `web/src/data/facilitatePipeline.ts` |
| Mode modal | `web/src/components/ChapterFacilitateModal.tsx` |
| Export serializer | `web/src/lib/exportMarkdown.ts` (anchor → footnote) |
| Eval harness | `src/services/chat/eval/facilitate_eval.py` |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| Service doc (SSE table + modes) | `docs/services/chat.md` |
| Reference graph | `docs/common ground/Elements/chat.html` |
| This doc | `docs/services/chat-features/53-facilitate-concept-map.md` |
| Tests | `src/services/chat/tests/test_facilitate_concept_map.py`, `web/src/components/FacilitateDigestCard.test.tsx` |
