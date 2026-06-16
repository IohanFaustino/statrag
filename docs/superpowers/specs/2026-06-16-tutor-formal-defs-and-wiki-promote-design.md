# Tutor mode — verbatim formal definitions + promoted Wikipedia

**Date:** 2026-06-16
**Status:** approved (design)
**Branch:** feat/component-equation-enforcement
**Base:** `3ef3e31` (checkpoint: prior-session tutor Wikipedia cited-source base)
**Builds on:** [2026-06-15 tutor Wikipedia cited source](2026-06-15-tutor-wikipedia-source-design.md)

## Problem

Two defects in tutor answers, observed on the canonical query
*"What is stationarity? What are the forms? What are the statistical tests used
to assess stationarity?"*

1. **Formal definitions are not reproduced verbatim.** The source corpus
   contains precise formal definitions (e.g. Hansen's *strict stationarity* and
   *weak/covariance stationarity*), but the tutor paraphrases them. The pipeline
   has a `formal_statement: str` field meant for verbatim reproduction, but it is
   (a) **singular** — one statement, while stationarity has **two** distinct
   forms each with its own definition — and (b) **gated to explicitly numbered
   labels** ("Definition 5.1.3"), so an unnumbered-but-formal definition never
   fires.

2. **Wikipedia is under-used.** The committed base wires Wikipedia as an
   **augment-only** source: appended at **trailing ranks**, labelled
   "supplementary", and the prompt forbids it from anchoring ("never to override
   a textbook"). Answers lean almost entirely on books.

## Decisions (locked with user)

| Question | Decision |
|---|---|
| **Formal defs — cardinality** | **Multiple.** A new list field holds every formal definition found (strict + weak each its own entry). |
| **Formal defs — gate** | **Relaxed.** Fires on any *explicitly stated* formal definition/theorem; a numbered label is preferred but **not required**. |
| **Formal defs — reuse** | **Brand-new tutor-only model.** Do NOT import facilitate's `FormalStatement` or any other mode's class/function. Mode isolation preserved. |
| **Wikipedia — promotion** | **Anchor + interleave.** Wiki may anchor a definition when the corpus lacks a clean formal one; interleaved at real ranks (not trailing-only); higher per-concept lookup. Still corpus-primary. |

## Architecture

### Part A — Verbatim formal definitions (tutor-only)

**Schema (`schemas/output.py`) — new model + field on `DeepTutorAnswer`:**

```python
class TutorFormalDef(BaseModel):
    kind: Literal["definition", "theorem", "proposition", "lemma", "corollary"]
    label: str = ""        # source's own label if any, e.g. "Definition 14.1"; "" when unlabelled
    statement: str = ""    # reproduced VERBATIM from source; display math in $$…$$
    cite: int              # [N] source rank backing this statement

    @model_validator(mode="after")
    def _statement_required(self): ...   # statement must be non-empty
```

- `DeepTutorAnswer.formal_statements: list[TutorFormalDef] = []` (new).
- Keep `formal_statement: str` field for **back-compat** with stored legacy
  conversations (rendered only when `formal_statements` is empty). New answers
  populate `formal_statements`; `formal_statement` stays `""`.
- Brand-new model — imports nothing from facilitate / qa / extension.

**Prompt (`prompts/deep_tutor.py`):** replace the single-`formal_statement`
instruction block (currently ~lines 240–261, the "CONDITIONAL … numbered formal
statement" rule) with: *"For EACH formal definition/theorem a source states
explicitly, emit one `formal_statements` entry reproducing it VERBATIM (the
source's own wording and notation; display math in `$$`). A numbered label is
preferred but not required — an explicitly-phrased definition qualifies. Cite
each with its `[N]`. Never paraphrase into this field; paraphrase belongs in
`definition`. Empty list when no source states one."* Examples updated to show
two entries (strict + weak).

**Backend (`deep_tutor.py`):** structured-output schema now carries
`formal_statements`. The back-compat mapper (`DeepTutorAnswer → TutorAnswer`)
serialises the list into the rendered markdown the frontend expects. No new
LLM call — same single narrative-draft call, richer schema.

### Part B — Wikipedia promotion (anchor + interleave)

**Backend (`deep_tutor.py`):**

- `_append_wiki_sources` → **interleave** wiki sources among corpus ranks instead
  of always trailing. Concrete rule: after corpus selection, splice each wiki
  source in at a real rank so it is not uniformly last (e.g. interleave 1-per-2
  corpus, or place anchoring wiki within the top band). Corpus sources keep
  relative order; wiki gets genuine visibility.
- Raise per-concept lookup: fetch top-N wiki summaries per concept (N bumped from
  1 → small constant, e.g. 2). Keep `asyncio.gather` concurrency + silent degrade.
- `TUTOR_DEEP_WIKI` kill switch unchanged.

**Prompt (`prompts/deep_tutor.py`, wiki render block ~lines 758–766):** drop the
"supplementary / never to override / never anchor" framing. New rule: *"Wikipedia
sources are valid evidence. Prefer the textbook corpus where it covers the
concept, but when the corpus lacks a clean formal definition, you MAY anchor the
`definition` (and a `formal_statements` entry, if Wikipedia states one verbatim)
on Wikipedia, cited by its `[N]` 🌐."* Corpus-primary preference stays; the
absolute prohibition is removed.

## Data flow (unchanged shape)

`extract concepts → (corpus retrieve ∥ wiki fetch) → coverage rerank →
interleave wiki → single narrative draft (schema w/ formal_statements) → seam
validate → SSE`. Only the source ranking and the draft schema change.

### Frontend

- **Render `formal_statements[]`**: each entry as a labelled verbatim block
  (`label` heading when present, KaTeX for `$$`), with its `[N]`/🌐 citation,
  wherever `formal_statement` renders today (`TutorView.tsx` /
  `mapConversationMessages.ts`). When `formal_statements` is empty, fall back to
  the legacy `formal_statement` string (back-compat).
- **`types.ts`**: add `TutorFormalDef` type + `formal_statements` on the tutor
  answer type.
- Wiki source rows already render 🌐 (committed base); interleaving changes only
  their rank/position, no new component.

### Lockstep artifacts (CLAUDE.md mandate)

- `src/services/chat/agents/deep_tutor.py`, `src/services/chat/prompts/deep_tutor.py`
- `src/services/chat/schemas/output.py` (new model + field)
- `web/src/types.ts`, `web/src/components/views/TutorView.tsx`,
  `web/src/lib/mapConversationMessages.ts` (+ render tests)
- Modal: `web/src/data/tutorPipeline.ts` + `web/src/components/PipelineDiagram.tsx`
  — node label note that the draft emits verbatim formal definitions; wiki node
  reflects "anchor + interleave" (+ `PipelineDiagram.test.tsx`)
- Docs: `docs/services/chat-features/36-deep-tutor.md` (mermaid + schema note +
  `TUTOR_DEEP_WIKI` row), `docs/services/chat-features/57-tutor-narrative.md`
  (formal_statements), `docs/system/invariants.md`, `docs/system/changelog.md`
- HTML: `docs/common ground/Elements/modes/tutor.html`
- Tests: `test_deep_tutor.py` (+ extend `test_tutor_wiki.py` for interleave/anchor)

## Error handling

- Wiki fetch failure → `wiki_evidence` returns `[]` → corpus-only, no surfaced
  error (unchanged). Interleave with an empty wiki list is a no-op.
- `formal_statements` empty is valid (no source states a formal def) → no heading
  rendered; back-compat string path also empty → nothing shown.
- `TutorFormalDef.statement` non-empty enforced by validator → no blank verbatim
  blocks.

## Testing

Backend:
- `formal_statements` with 2 entries (strict + weak) round-trips through the
  structured schema and the back-compat mapper into rendered markdown.
- Relaxed gate: an unlabelled-but-explicit definition produces an entry; pure
  prose with no formal statement produces `[]`.
- Empty-statement entry rejected by validator.
- Wiki interleave: wiki sources land at non-trailing ranks; corpus relative
  order preserved; `TUTOR_DEEP_WIKI=0` → no wiki, no interleave.
- Anchor allowed: prompt no longer contains the "never override/anchor" string
  (string-presence assertion on the rendered prompt) — true-by-test.

Frontend:
- `formal_statements[]` renders each labelled verbatim block with KaTeX + cite.
- Empty `formal_statements` + legacy `formal_statement` string → legacy render.

## Live verification (the gate)

On `:5175`, query verbatim:
*"What is stationarity? What are the forms? What are the statistical tests used
to assess stationarity?"*

PASS requires:
1. **Strict** and **weak/covariance** stationarity each shown as a **verbatim**
   formal definition (matches source wording, KaTeX renders).
2. At least one **Wikipedia** source cited 🌐, interleaved (not buried last) —
   ideally anchoring a definition or the stationarity-tests breadth.
3. Statistical tests (ADF / KPSS / PP etc.) covered.
4. Zero console errors; reload persistence intact.

Certified by a **sonnet browser agent** (claude-in-chrome). Iterate until PASS.

## Out of scope (YAGNI)

- Wiki caching / formula_cache-style store.
- Per-section Wikipedia (summaries only).
- Co-equal primary ranking for Wikipedia (stays corpus-primary).
- Changing the single narrative-draft topology (schema-only enrichment).
