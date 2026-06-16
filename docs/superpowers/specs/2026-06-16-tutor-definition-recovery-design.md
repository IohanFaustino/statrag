# Tutor mode — Definition Recovery (premium verbatim formal definitions)

**Date:** 2026-06-16
**Status:** approved (design)
**Branch:** feat/component-equation-enforcement
**Supersedes (partially):** the "true-by-instruction" half of
[2026-06-16 formal-defs + wiki](2026-06-16-tutor-formal-defs-and-wiki-promote-design.md).
That spec's schema (`TutorFormalDef`) and render path **stay**; its reliance on the
draft model to *populate* `formal_statements` from a prompt instruction is **replaced**
by code-built entries from a dedicated retrieval.
**Mirrors:** the live `formula_recovery` trio
(`formula_gaps.py` / `formula_recovery.py` / `formula_cache.py`).

## Problem (live-verified 2026-06-16)

On *"What is stationarity? What are the forms? What are the tests?"* the tutor
answer had **no verbatim formal definitions**. Two architectural failures:

1. **Retrieval never fetched the formal definition.** The main hybrid retrieval
   optimizes broad relevance for the whole question; the labelled *Definition*
   chunk (e.g. Hansen's strict/weak stationarity) loses that broad contest and
   never enters the top-k pool. It was absent — sources were
   spark_ts/atwan/cerqueira/wooldridge/wiki, **no Hansen**.
2. **No verbatim protection.** Even when a formal def *is* in the pool, the draft
   model (gpt-5.4-nano) paraphrases it. `formal_statements` was left empty because
   it is optional and the model takes the easy path.

**Conclusion:** the formal definition is *premium information*. It needs its own
targeted retrieval and must be reproduced **verbatim by construction**, not by
asking the model nicely.

## Decisions (locked with user)

| Question | Decision |
|---|---|
| **Architecture** | **Mirror `formula_recovery`**: new `definition_gaps.py` / `definition_recovery.py` / `definition_cache.py`. Gap-detect → dedicated targeted retrieval → verbatim extract → cache → inject. |
| **Who builds `formal_statements`** | **Pure code (true-by-construction).** Recovery extracts verbatim; CODE constructs `formal_statements[]`. The draft only weaves prose around them and cannot paraphrase them away (like the pure-code citation bind in QA/extension/facilitate). |
| **Extraction** | **LLM-extract + code fidelity gate.** A cheap LLM pulls the definition span (strict "copy verbatim"); pure-code token-recall vs the source chunk rejects any paraphrase/hallucination. |

## Architecture (end-to-end)

```
concept extraction
   ├─ main retrieval (general, unchanged) ──────────────┐
   ├─ wiki augment (unchanged) ─────────────────────────┤
   └─ DEFINITION RECOVERY (NEW, parallel, PREMIUM):      │
        detect_definition_gaps(concepts, query, sources) │  # which concepts the query asks to DEFINE
        → recover_definitions(gap, books)                │  # DEDICATED query per concept (this fetches Hansen)
        │     • targeted retrieval: "formal definition of {concept}",
        │       BM25-boosted for definition-bearing chunks
        │     • LLM-extract verbatim span {kind,label,statement}
        │     • CODE fidelity gate: token-recall(statement, chunk) ≥ θ → else drop
        │     • definition_cache lookup/write (Qdrant)
        ▼                                                 │
   sources += recovered-def source rows (real citations) ◄┘
   →  draft(DeepTutorAnswer) with <formal_definitions> block injected
   →  CODE OVERRIDE: answer.formal_statements = build_formal_statements(recovered)
   →  seam validate → SSE
```

### New modules (parallel to `formula_*`)

**`definition_gaps.py`**
- `DefinitionGap` dataclass: `concept: str`, `norm: str`.
- `detect_definition_gaps(concepts, query, sources) -> list[DefinitionGap]`:
  a concept is a gap when the query is **definitional** for it (query contains
  "what is / define / definition of / forms of / strict / weak …", or the concept
  is a central anchor) AND the retrieved `sources` do not already yield a
  code-extractable labelled/formal definition for it. Premium concepts are always
  considered. Returns at most ~3 gaps (cost bound).

**`definition_recovery.py`**
- `RecoveredDefinition(BaseModel)`: `concept`, `kind`
  (`definition|theorem|proposition|lemma|corollary`), `label`, `statement`
  (VERBATIM), and citation fields (`book`, `book_name`, `chapter`, `section`,
  `page_from/to`, `chunkId`).
- `async recover_definitions(query, gaps, books) -> list[RecoveredDefinition]`:
  per gap (concurrent `asyncio.gather`):
  1. **cache_lookup** → hit returns immediately.
  2. **dedicated retrieval**: `hybrid_search` with a definition-shaped query
     (`"formal definition of {concept}"`) over the book collections; rerank with a
     definition-bearing boost (chunks containing `Definition N`, `is said to be …
     if`, `is (strictly|weakly) … if`). Take top 1–2 candidate chunks.
  3. **LLM-extract** (cheap model): "Reproduce the formal definition WORD FOR WORD
     incl. its label and any `$$…$$`; output `{kind,label,statement}` or null if
     the chunk states none." Multiple forms allowed (strict AND weak → 2).
  4. **fidelity gate (PURE CODE)**: `token_recall(statement, chunk_text) ≥ θ`
     (θ≈0.9). Fail → drop (never fabricate).
  5. **cache_write**.
- `build_formal_statements(recovered, sources) -> list[TutorFormalDef]`: **PURE
  CODE** map RecoveredDefinition → `TutorFormalDef(kind, label, statement, cite)`,
  where `cite` is the rank of the recovered-def source after it's appended to the
  sources pool. This is the true-by-construction bind.
- `format_definitions_block(recovered) -> str`: a `<formal_definitions>` block for
  the draft system message so the prose *references* them — the draft must NOT
  author the verbatim entries (they are code-owned).

**`definition_cache.py`** (mirror `formula_cache.py`)
- Qdrant `definition_cache` collection. `async cache_lookup(concept, threshold=0.93)`,
  `async cache_write(concept, kind, label, statement, citation)`; embedding-keyed.

### Integration — `deep_tutor.py`
- Launch `recover_definitions` concurrently with retrieval + wiki (`asyncio.gather`),
  gated by env `TUTOR_DEEP_DEFINITIONS` (default `"1"`, `"0"` disables).
- Append each RecoveredDefinition's source chunk to `sources` (so its `[N]` cite
  resolves) and to `citations` (verbatim `quote` = the definition).
- Inject `format_definitions_block(recovered)` into the draft system message.
- After the draft returns: **override** `answer.formal_statements =
  build_formal_statements(recovered, sources)` (drop the model's own — code owns it).
- Existing render (`_render_formal_statements`, Task 2) renders them under the
  Formalize beat unchanged.

### Prompt change (`prompts/deep_tutor.py`)
- The `formal_statements` instruction becomes: "These are provided to you VERBATIM
  in `<formal_definitions>` and are inserted by the system — do NOT author or
  paraphrase them; weave your prose to introduce and explain them, referencing
  each by its `[N]`." (Removes the burden of the model populating them.)

## Why this fixes both failures
- **Failure 1 (not retrieved):** the *dedicated definition query* ranks the
  labelled-definition chunk highly because it's definition-shaped vs a
  definition-shaped query — Hansen surfaces even though it lost the broad contest.
- **Failure 2 (paraphrase):** the verbatim text is extracted + fidelity-gated in
  code and the `formal_statements` entries are **code-built**; the model never gets
  to paraphrase them.

## Error handling
- Any recovery failure / no formal def found / fidelity-gate reject → empty list →
  `formal_statements` empty → "Formal statement" heading dropped (graceful, exactly
  as corpus-only today). Never blanks the turn. `TUTOR_DEEP_DEFINITIONS=0` fully
  bypasses.

## Testing
Backend:
- `detect_definition_gaps`: definitional query + concept w/o def in sources → gap;
  non-definitional query → no gap.
- fidelity gate: paraphrased statement (low token-recall) → dropped; verbatim → kept.
- `build_formal_statements`: RecoveredDefinition list → `TutorFormalDef[]` with
  correct `cite` indices; verbatim `statement` preserved.
- integration (mocked retrieval+LLM): two recovered defs (strict+weak) →
  `answer.formal_statements` has 2 verbatim entries regardless of what the mocked
  draft emitted (proves code override).
- `TUTOR_DEEP_DEFINITIONS=0` → no recovery, no override.

## Live gate
Same query on :5175 must now show a **Formal statement** section with **strict**
and **weak** stationarity reproduced **verbatim** (matching a real corpus chunk —
ideally Hansen), each cited `[N]`, KaTeX rendered. 0 console errors.

## Lockstep artifacts
- New modules + tests (above).
- `deep_tutor.py` wiring; `prompts/deep_tutor.py` formal_statements instruction.
- Frontend structured `formal_statements[]` render (the prior plan's Task 6 — still needed).
- Modal `tutorPipeline.ts` + `PipelineDiagram.tsx`: new **"Definition recovery"**
  node parallel to retrieval (mirror the formula-recovery node) + test.
- Docs: new feature doc `docs/services/chat-features/58-definition-recovery.md`;
  `36-deep-tutor.md` mermaid + `TUTOR_DEEP_DEFINITIONS` env row; `invariants.md`;
  `changelog.md`; HTML `modes/tutor.html`.

## Out of scope (YAGNI)
- Vision/figure extraction of definitions (text chunks only; that's formula_recovery's job).
- Cross-book definition reconciliation (if two books define differently, recover each as its own entry — no merging).
- definition_cache eviction/TTL (mirror formula_cache: write-once, embed-keyed).

## Phasing (build order)
1. `definition_gaps.py` + `definition_recovery.py` (+ `build_formal_statements`, fidelity gate) + tests — the core.
2. `definition_cache.py` + tests.
3. `deep_tutor.py` wiring + prompt + integration test.
4. Frontend structured render (prior Task 6).
5. Modal + docs lockstep.
6. Live verify (stationarity → verbatim strict+weak).
