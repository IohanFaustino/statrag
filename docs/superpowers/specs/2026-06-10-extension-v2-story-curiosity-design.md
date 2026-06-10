# Extension v2 — Story timeline + curiosity boxes (design)

**Date:** 2026-06-10 · **Status:** approved by user (sections §1–§6, brainstorming session)
**Replaces:** the deepagents topology-C extension core (spec 2026-06-09). Mode id stays `extension`.
**Branch base:** `feat/component-equation-enforcement`.

## 1. Problem

The shipped extension mode produced output that misses the user's intent and has four
citation defects observed live:

1. Footnote sources are model-asserted free-text strings — unverifiable.
2. Cross-book corpus retrieval misses passages that exist in other ingested books.
3. Wikipedia citations are weak (missing/wrong URLs, no titles).
4. Too few references per item overall.

Additional live defects traced to the free-form deepagents orchestrator: language drift
(Polish), sequential analyst calls (~17 min runs), scope widening, opaque judge loop.

## 2. Intent (user's mental model)

1. **Timeline** — a story that follows the sequence the author built in the original
   text. Every section is a **take**: identify its pieces of information and narrate
   them. The timeline is the primary reading surface.
2. **Curiosity box** — expansion of the story. Each bullet is a **subject**, collected
   from BOTH other corpus books and Wikipedia, **always cited**.
3. **Decoupling** — augmentation never alters the timeline. It is a robust extra:
   a collapsed **toggle card** per take in the frontend; **numbered footnotes** in the
   ZIP export.
4. **Agent = Harness + model** — every pipeline stage is declared as a harness
   (tools, prompt scaffold, structured output schema) plus an explicit model.

## 3. Architecture — deterministic LangGraph pipeline (approach A, chosen)

One async `StateGraph` replaces the deepagents core inside
`src/services/chat/agents/extension_agents/`. Two pure-code stages carry the trust;
LLM stages are small, structured-output-enforced, English-pinned. Parallel fan-out via
langgraph `Send`. Embedder + reranker warmed on the main thread before the graph runs
(carries the `_warm_retrieval` lesson).

```
scope → fetch ─Send→ storyteller ×N ─→ story_editor ─Send→ subject_miner ×take
      ─Send→ researcher ×subject (CODE) ─Send→ curiosity_writer ×take
      → citation_binder (CODE) → judge (bounded retry) → StoryDigest
```

### Agent roster

| Agent | Harness | Model (default; overridable via `extensionModels`) |
|---|---|---|
| `scope_resolver` | existing `aresolve_scope_or_clarify` + authoritative clamps: runner always stamps `digest.book`/`digest.chapter`; `_scope_label` narrowed label; `_needle_matches` section matching | nano |
| `storyteller` ×section | 1 section = 1 take. Input: section text + previous take heading (continuity). Output `TakeDraft{heading, story, key_items[]}`. Story register, author's sequence, ENGLISH pinned. | nano, parallel |
| `story_editor` | stitches takes into one continuous voice. Hard rules: NO new facts; ≤10% length growth. | nano |
| `subject_miner` ×take | curiosity subjects from take + key_items; gap taxonomy (formal-def / derivation / comparative / application / history). Output `Subject{title, queries[2–3]}`. | nano, parallel |
| `researcher` ×subject | **pure code, no LLM**: multi-query `hybrid_search` cross-book (exclude target book, rerank ON, score floor, `seen_ids` dedupe) + Wikipedia REST (search → summary; title + URL + extract). Output `Evidence{id, kind, text, meta}`. Target ≥4 evidence per subject (≥2 corpus + ≥2 wiki when available). | — |
| `curiosity_writer` ×take | writes bullets FROM evidence only; each bullet lists `evidence_ids`; **forbidden to write citation text**. | nano, parallel |
| `citation_binder` | **pure code**: maps `evidence_ids` → `Citation` objects copied **verbatim** from retrieval payloads (book_name/authors/year/chapter/section_id/pages, or wiki title+URL) + `chunk_id` provenance. Bullets with zero valid ids are dropped and logged to `unfilled_subjects`. | — |
| `judge` ×take | coverage check (each subject answered, ≥1 bullet); ONE bounded retry of miner→researcher→writer for failed takes, then accept with gaps listed. | nano |

The binder removes the "model-asserted sources" class of bug mechanically; the code
researcher turns retrieval quality into tunable knobs (multi-query, rerank, floor)
instead of LLM whim; evidence targets address reference density; the Wikipedia REST
path always yields title + URL.

## 4. Schema v2 (`schemas/output.py`; `ExtensionDigest` kept for legacy convs)

```python
class Citation(BaseModel):
    kind: Literal["corpus", "wikipedia"]
    label: str                      # binder-built render string
    book_slug: str | None = None
    book_name: str | None = None
    authors: str | None = None
    year: int | None = None
    chapter: str | None = None
    section_id: str | None = None
    pages: str | None = None
    title: str | None = None        # wikipedia
    url: str | None = None          # wikipedia
    chunk_id: str | None = None     # corpus provenance

class CuriosityItem(BaseModel):
    subject: str
    body: str                       # prose w/ $-math; from evidence only
    citations: list[Citation]       # ≥1, binder-enforced

class Take(BaseModel):
    heading: str
    story: str
    items: list[CuriosityItem]      # may be []

class StoryDigest(BaseModel):
    book: str                       # runner-stamped
    chapter: str                    # honest narrowed label
    takes: list[Take]
    unfilled_subjects: list[str]
```

Persisted content carries `_schema = "StoryDigest"`; `mapConversationMessages` revives
by `_schema`, so old `ExtensionDigest` conversations keep rendering on the old card.
No DB migration.

## 5. SSE contract (same event vocabulary; new `stage` keys only)

```
meta {mode:"extension", model, books}              ← always first (badge)
stage {stage:"parse"}    stage {stage:"fetch"}
stage {stage:"story", label:"Take k/N — <heading>"}   ×N, streamed as each lands
stage {stage:"edit"}     stage {stage:"research"}
stage {stage:"write"}    stage {stage:"bind"}     stage {stage:"judge"}
structured_output {schema:"StoryDigest", data}
sources_full {sources:[…]}                         ← real evidence list (side panel populated)
usage / done
```

Frontend reuses the skeleton mechanism: `stage{story}` events render take headings live.
Persistence: content = StoryDigest JSON + `_schema`; metadata `{"turnMode":"extension"}`.

## 6. Frontend — `StoryDigestCard` (layout A, approved)

- **Timeline rail**: numbered nodes down the left (take sequence), connecting line.
- Take = heading + story prose.
- Under each take: collapsed toggle **"▸ Curiosity box (N)"**; expands to bullets.
- Citation chips per bullet: 📕 corpus (label w/ book + section + pages; hover = full
  ref), 🌐 wikipedia (opens article in new tab).
- **Formatting (user-mandated):** story AND curiosity bodies render structured text
  (bold/italic/markdown via the shared `renderMathText` + inline-markdown renderer)
  **and KaTeX math**; both use `text-align: justify`.
- Header: `book · chapter — Story` + Download ZIP + **expand-all / collapse-all**.
- Legacy `ExtensionDigest` convs keep `ExtensionDigestCard` (schema-keyed dispatch in
  `MessageThread`).

## 7. ZIP export

`POST /api/export` accepts StoryDigest (and still ExtensionDigest for legacy). HTML:
title block → takes in author sequence (justified prose, KaTeX) → curiosity items as
**numbered footnotes anchored at each take's end** (subject = footnote heading; full
citation labels; clickable wiki URLs). `sources.json` = evidence list. Filename
sanitized (no `·`/`–`/spaces).

## 8. Error handling

- Each LLM stage: 1 structured-parse retry with repair prompt.
- Storyteller failure → take degrades to flagged raw-section summary.
- Researcher empty / writer drop / binder drop → subject recorded in
  `unfilled_subjects`. The pipeline never aborts a whole run for one take.
- Judge: ONE bounded retry per failed take.

## 9. Testing

- Unit tests per node with fixture evidence.
- **Binder property test: every rendered citation field exists verbatim in some
  evidence payload** — the verifiability guarantee.
- Prompt scaffold tests (English pin, no-new-facts rule, parallel directives gone —
  obsolete in v2).
- Frontend card tests: toggle behavior, justify class, KaTeX + markdown in story and
  box, citation chips, expand/collapse-all, legacy card dispatch.
- E2E graph test with mocked LLM + retrieval; ZIP golden test.

## 10. Lockstep artifacts

doc 54 rewrite (new mermaid), `docs/common ground/Elements/modes/extension.html`,
new invariant ("citation fields copied verbatim from retrieval payloads — never
model-generated"), changelog entry, modal pipeline card data.

## 11. Deletions

`extension_agents/agent.py` (deepagents build), `extension_skills/` (all three
SKILL.md), deepagents-specific prompts. Reused/reworked: `scope.py`, retrieval tools,
`export.py`, runner SSE scaffolding.
