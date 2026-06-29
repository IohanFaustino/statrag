# 58 — Definition recovery + formula recovery (formal_statements[])

## Purpose

Two complementary best-effort recovery stages run between Wikipedia augment and
Figure judge in `run_deep_tutor`:

1. **Formula recovery** (`_recover_equations_block`) — detects when a defining
   equation was OCR-dropped to an image placeholder and recovers the LaTeX via a
   waterfall: formula cache → vision read of the figure (gpt-4o) → formula-scoped
   text re-query. Recovered equations are injected verbatim into the draft as a
   `<recovered_equations>` block. Pure code + vision; never blocks the answer.

2. **Definition recovery** (`_recover_definitions_block`) — detects definitional
   gaps (concepts whose source chunks lack a verbatim formal definition), runs a
   dedicated hybrid retrieval per gap, scores token-recall against source chunks,
   and formats recovered statements as a `<formal_definitions>` block for the
   draft. Pure code (no LLM/vision); gated by `TUTOR_DEEP_DEFINITIONS` (default
   `1`); never blocks the answer.

A third, related change surfaces recovered *and* LLM-stated definitions and
theorems as **structured `formal_statements[]`** on `TutorAnswer` (and its
internal `DeepTutorAnswer`), so the frontend can render them as labelled
blockquotes with citation pills — a richer path than the legacy text-only
`formal_statement` string field.

## Formal statements schema

```python
class TutorFormalDef(BaseModel):
    kind: Literal["definition", "theorem", "proposition", "lemma", "corollary"]
    label: str       # e.g. "Definition 14.1" — empty string falls back to kind
    statement: str   # Verbatim or reconstructed LaTeX/prose
    cite: int        # 1-based citation index referencing TutorCitation[]
```

`DeepTutorAnswer` gains an optional `formal_statements: list[TutorFormalDef]`
(default empty). The frontend `TutorView` checks for
`data.formal_statements.length > 0`; when present it renders each entry as a
labelled blockquote (bold kind/label prefix + statement body + `[N]` citation
pill) *above* the text-parsed sections. When absent (legacy answers), the old
`## Formal statement` section parsed from `data.text` continues to render as a
collapsible section — the fallback is seamless.

## Pipeline position

Both recovery stages sit between **Wikipedia augment** and **Figure judge** in
the deep-tutor pipeline:

```
… → coverage → wiki → formula recovery + definition recovery → figure judge → plan → draft → …
```

Both are best-effort — they never raise to their caller and never block the
answer. Any failure anywhere degrades silently to today's behaviour (no recovered
equations/definitions, `formal_statements` left empty).

## Frontend render path

| Condition | Render path |
|---|---|
| `data.formal_statements` present and non-empty | `renderFormalStatements()` — labelled blockquotes above sections |
| `data.formal_statements` absent or empty, but `data.text` has `## Formal statement` | Legacy: `splitIntoBlocks` → collapsible section with quote |

`mapConversationMessages` preserves the full structured payload (including
`formal_statements`) when reviving a stored `TutorAnswer` from the
conversations API, so reloaded conversations render correctly.

## Files

| Path | Role |
|---|---|
| `src/services/chat/agents/formula_gaps.py` | `detect_formula_gaps` — pure, detects OCR-dropped equations |
| `src/services/chat/agents/formula_recovery.py` | `recover_formulas` — per-gap waterfall (cache → vision → re-query) |
| `src/services/chat/agents/formula_cache.py` | Global Qdrant `formula_cache` collection |
| `src/services/chat/agents/definition_gaps.py` | `detect_definition_gaps` — pure, detects definitional gaps |
| `src/services/chat/agents/definition_recovery.py` | `recover_definitions` — dedicated hybrid retrieval per gap, token-recall scoring |
| `src/services/chat/agents/definition_cache.py` | Global Qdrant `definition_cache` collection |
| `src/services/chat/agents/deep_tutor.py` | `_recover_equations_block` + `_recover_definitions_block` wiring, `DeepTutorAnswer.formal_statements` |
| `src/services/chat/schemas/output.py` | `TutorFormalDef`, `TutorAnswer.formal_statements` |
| `web/src/types.ts` | `TutorFormalDef`, `TutorAnswer.formal_statements` |
| `web/src/components/views/TutorView.tsx` | `renderFormalStatements` — labelled blockquotes |
| `web/src/data/tutorPipeline.ts` | `def_recovery` node |
| `web/src/data/tutorMode.ts` | Updated "Verbatim theorems" + "Multi-aspect answer" wording |
| `web/src/lib/mapConversationMessages.ts` | Preserves `formal_statements` in structured payload |

## Invariant

See invariant 37 in `docs/system/invariants.md` for the best-effort contract.

## DR-8d — vision fallback for image-bound definitions

When the text path (cache → hybrid retrieval → verbatim extract + token-recall
gate) is exhausted — i.e. no candidate chunk yielded a verbatim text
definition — **and** at least one candidate chunk carried an OCR image
placeholder (`![image](…)`), definition recovery chains to
`formula_recovery`'s vision path (`search_figures` + `inspect_figure`) to
transcribe the defining equation for the gap concept. The transcribed LaTeX
is wrapped (if needed) in `$…$` and used verbatim as the `RecoveredDefinition`
formal `statement`.

- **Fidelity = vision-trusted.** The pure-code token-recall gate
  (`is_verbatim`) is intentionally NOT applied to the vision output: there is
  no clean source text to compare against, and `formula_recovery` already
  vouches for the transcribed LaTeX (same trust boundary as equation
  recovery).
- **Best-effort under `TUTOR_DEEP_DEFINITIONS`.** No new env flag; the whole
  fallback sits behind the existing definition-recovery gate. Any failure
  (vision returns no equation, empty latex, or an exception) degrades
  silently to `None` — never raises, never blocks the answer.
- **Citation.** `book_name` carries the figure citation string from the
  recovered equation so `_def_sources` still yields a usable citation row;
  book/chapter/page are left empty when not available from the equation.

## DR-9 — concept-relevance gate + reranked dedicated retrieval

The dedicated retrieval in `_recover_one` now **reranks** (cross-encoder) by
calling `hybrid_search(..., rerank=True, rerank_top_n=5)` so on-topic chunks
rank first (previously `rerank=False` surfaced off-topic chunks at the top —
live: for "weak stationarity" the top hits were an `agentic_patterns` chunk
and a `peters` causal-inference chunk). On top of the rerank, a **pure-code
concept-relevance gate** (`_concept_relevant`) drops any extracted definition
that shares no concept token with the query: at least one substantive concept
token (alphanumeric, length ≥ 4 after dropping stopwords a/an/the/of/for/and/
or/to/in/is) must appear, by a short stem-prefix (first min(len,6) chars), in
the lowercased statement+label. This prevents an off-topic verbatim definition
(e.g. the labelled "Definition 6.32 (Causal graphical model)" from a peters
chunk) from reaching the user even when `is_verbatim` passes.