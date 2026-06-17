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