# Feature 53 — Facilitate story mode (story remake, 2026-06-12)

**Branch:** `feat/facilitate-story-remake`
**Date:** 2026-06-12
**Original concept-map spec:** [`docs/superpowers/specs/2026-06-01-facilitate-concept-map-design.md`](../../superpowers/specs/2026-06-01-facilitate-concept-map-design.md)
**Story remake spec:** [`docs/superpowers/specs/2026-06-12-facilitate-story-remake-design.md`](../../superpowers/specs/2026-06-12-facilitate-story-remake-design.md)
**Story remake plan:** [`docs/superpowers/plans/2026-06-12-facilitate-story-remake.md`](../../superpowers/plans/2026-06-12-facilitate-story-remake.md)

---

## Summary of the rebuild

The original facilitate mode looped over all sections of a chapter, teaching each via concept-map extraction + sub-retrieval + simplification. The rebuild replaces that loop with a **single-section story pipeline**: exactly one section per request, narrated as a connected story (hook → movements → takeaway) with verbatim formal statements unpacked didactically. Pure-code bind and statement-fidelity verify replace the old LLM verify node.

The legacy `FacilitateDigest` schema and its renderer are retained for old stored conversations.

---

## Pipeline

```
parse + resolve scope (LLM, model key "map")
        │
        ├─ ambiguous book/section ──► clarify (data — stop + ask)
        │
        ▼
fetch ONE section (data)
        resolve ONE section via closest-match + confirm
        pull that single section from Qdrant
        │
        ▼
map (LLM, model key "map")
        extract key concepts / theorems / formulas as [[cN]] anchors
        │
        ▼
write story (LLM, model key "write")
        hook → movements → takeaway
        formal statements reproduced VERBATIM then unpacked
        (elements → associations → intuition → concise close)
        │
        ▼
bind (PURE CODE)
        attach concept provenance + 📕 corpus citations verbatim
        strip [[cN]] anchors the writer invented with no matching concept
        │
        ▼
verify (PURE CODE — statement fidelity)
        token-recall of each formal statement against the source text
        sets grounding badge
        │
        ▼
FacilitateStory ──► SSE structured_output
```

### Mermaid

```mermaid
flowchart TD
  U[user message] --> PR[parse + resolve scope\nLLM · model key map]
  PR -->|ambiguous| CL[clarify\nstop + ask]
  PR -->|confident| FE[fetch ONE section\nclosest-match + confirm]
  FE --> MAP[map · concept extraction\n[[cN]] anchors · LLM]
  MAP --> WR[write story\nhook → movements → takeaway\nverbatim formal statements unpacked · LLM]
  WR --> BD[bind · PURE CODE\nprovenance + 📕 citations verbatim\nstrip invented anchors]
  BD --> VRF[verify · PURE CODE\nstatement fidelity token-recall\nsets grounding badge]
  VRF --> FS[FacilitateStory]
  style WR fill:#3a1d1f,stroke:#E5484D,color:#fff
  style BD fill:#1a2233,stroke:#4da6ff,color:#fff
  style VRF fill:#1a2233,stroke:#4da6ff,color:#fff
  style CL fill:#2a1a1a,stroke:#d2624c,color:#fff
```

---

## One-section rule

Facilitate teaches exactly **one section per request**. The runner:

1. Resolves the book + chapter via `resolve_book` (LLM fuzzy match against the catalog).
2. Fetches all section headings for the chapter via `fetch_chapter_sections`.
3. Calls `resolve_section(message, subtopics, headings)` — a pure-code closest-match (fuzzy title + subtopic overlap) that returns a single `section_id` or `None`.
4. If `None` → emits `section_clarify(headings=…)` and stops.
5. Fetches the single section `Source` object.

There is no section loop. Each request teaches one section; if you want the next section, send another message.

---

## Verbatim formal statements

The write prompt instructs the model to handle formal statements (definition / lemma / theorem / proposition / corollary / remark) with a two-step protocol:

1. **Reproduce verbatim** — copy the statement exactly as it appears in the source.
2. **Unpack didactically** — four sub-moves:
   - *Elements*: name each symbol and variable.
   - *Associations*: link each element to prior concepts.
   - *Intuition*: one sentence of geometric or causal insight.
   - *Concise close*: one sentence tying the statement back to the story.

The pure-code verify stage (`statement_fidelity`) checks that each formal statement passes ≥ 60% token-recall against the source section text. Failures set `grounding.ok = False`.

---

## Concept anchors and ConceptChat

The map node extracts up to `FACILITATE_MAX_CONCEPTS` (default 5) concepts/theorems/formulas per section and assigns each a `[[cN]]` id. The write node embeds these markers in the story prose.

The bind step:
- Keeps only anchors whose id appears in the story text (`bind_concepts`).
- Strips `[[cN]]` markers that reference no valid anchor (`strip_unbound_markers`).
- Attaches `ConceptProvenance` from the source section payload (book, authors, section title, pages).
- Builds `StoryCitation` records verbatim from the `Source` object (never model-authored).

The frontend renders `[[cN]]` markers as clickable concept pills. Clicking a pill opens the **ConceptChat side panel** which hits `POST /api/concept/explore` (stateless, no conversation store read/write) with the concept term + provenance context. The side panel supports a "deepen" follow-up question.

---

## Schemas

Defined in `src/services/chat/schemas/output.py`.

```python
class FormalStatement(BaseModel):
    kind: str          # "definition" | "lemma" | "theorem" | "proposition" | "corollary" | "remark"
    statement: str     # verbatim reproduction
    explanation: str   # didactic unpack

class Movement(BaseModel):
    prose: str | None = None
    formal: FormalStatement | None = None   # XOR with prose

class FacilitateStoryDraft(BaseModel):
    hook: str
    movements: list[Movement]
    takeaway: str
    math_blocks: list[str]

class FacilitateStory(BaseModel):
    mode: Literal["facilitate_story"]
    scope: ChapterScope
    hook: str
    movements: list[Movement]
    takeaway: str
    concepts: list[ConceptAnchor]
    citations: list[StoryCitation]
    math_blocks: list[str]
    grounding: dict    # {ok, unsupported, confidence}
```

`FacilitateStory` is emitted as `structured_output{schema:"FacilitateStory"}` on every new facilitate turn. The legacy `FacilitateDigest` (mode `"facilitate"`) is retained for old stored conversations and rendered by the legacy `FacilitateDigestCard`.

---

## SSE stage keys

| Stage key | Kind | Description |
|---|---|---|
| `parse` | LLM | Parse + book/chapter resolve |
| `map` | LLM | Concept extraction per section |
| `write` | LLM | Story narrative generation |
| `verify` | PURE CODE | Statement fidelity check + grounding badge |

`stageModels` overrides apply to `parse`, `map`, `write`. `bind` and `verify` are pure code — no model override.

---

## Env flags

| Var | Default | Effect |
|---|---|---|
| `FACILITATE_MAX_CONCEPTS` | `5` | Max `[[cN]]` anchors per section |
| `CHAPTER_CLARIFY` | `1` (shared) | Kill-switch for book-scope clarify gate |

---

## ConceptChat endpoint

`POST /api/concept/explore` — stateless, no conversation store.

Request body:
```json
{
  "term": "maximum likelihood estimation",
  "provenance": { "book_slug": "...", "section": "..." },
  "followUp": "Why does it maximize the log-likelihood?"
}
```

Response: SSE stream with `text` delta events, followed by `done`. The endpoint retrieves corpus + Wikipedia context and writes a short explanatory answer. It never reads or writes the conversation store (invariant).

---

## Frontend

| Component / file | Path | Role |
|---|---|---|
| `FacilitateStoryCard` | `web/src/components/FacilitateStoryCard.tsx` | Renderer for `FacilitateStory`; hook → movements (prose / formal) → takeaway → concept pills → grounding badge |
| `ConceptChat` | `web/src/components/ConceptChat.tsx` | Side panel opened by concept pill clicks; hits `/api/concept/explore` |
| `FACILITATE_PIPELINE` | `web/src/data/chapterPipeline.ts` | 7-node pipeline data (parse/fetch/map/write/bind/verify/clarify) |
| `FACILITATE_MODE` | `web/src/data/chapterMode.ts` | Modal blurb + feature list |
| `ChapterFacilitateModal` | `web/src/components/modals/ChapterFacilitateModal.tsx` | (i) modal; LLM stage overrides: parse / map / write only |
| `MessageThread` | `web/src/components/MessageThread.tsx` | Discriminates on `schema === "FacilitateStory"` → `<FacilitateStoryCard>` |

---

## Legacy compatibility

`FacilitateDigest` (mode `"facilitate"`, pre-remake) conversations still render via `FacilitateDigestCard`. The discriminator in `MessageThread.tsx` routes on `schema`:
- `"FacilitateStory"` → new `FacilitateStoryCard`
- `"FacilitateDigest"` → legacy `FacilitateDigestCard`

No DB migration required.

---

## Synced-artifacts checklist

A logic change to the facilitate story pipeline is incomplete until **all** of these reflect it:

| Aspect | Path |
|---|---|
| Runner | `src/services/chat/agents/facilitate_story.py` |
| Binder / fidelity | `src/services/chat/agents/facilitate_story.py` (pure-code helpers) |
| Prompts | `src/services/chat/prompts/chapter.py` (FACILITATE_STORY_WRITE_PROMPT, FACILITATE_MAP_PROMPT) |
| Scope helpers | `src/services/chat/agents/_scope.py` (resolve_section, section_clarify) |
| Output schemas | `src/services/chat/schemas/output.py` (FacilitateStory, FacilitateStoryDraft, Movement, FormalStatement) |
| ConceptChat endpoint | `src/services/chat/api.py` (POST /api/concept/explore) |
| Mode registration | `src/services/chat/modes.py` |
| Frontend types | `web/src/types.ts` |
| Story renderer | `web/src/components/FacilitateStoryCard.tsx` + `MessageThread.tsx` |
| Concept side panel | `web/src/components/ConceptChat.tsx` |
| Pipeline data | `web/src/data/chapterPipeline.ts` (FACILITATE_PIPELINE) |
| Mode data | `web/src/data/chapterMode.ts` (FACILITATE_MODE) |
| Mode modal | `web/src/components/modals/ChapterFacilitateModal.tsx` |
| Markdown doc | `docs/services/chat-features/53-facilitate-concept-map.md` (this file) |
| HTML doc | `docs/common ground/Elements/modes/facilitate.html` |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| Tests | `src/services/chat/tests/test_facilitate_story.py`, `web/src/components/FacilitateStoryCard.test.tsx` |
