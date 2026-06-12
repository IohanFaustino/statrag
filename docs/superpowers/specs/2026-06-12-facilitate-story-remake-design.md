# Facilitate Story Remake — Design Spec

**Date:** 2026-06-12
**Status:** Draft — awaiting user review
**Branch (planned):** `feat/facilitate-story-remake` (isolated worktree)
**Mode touched:** `facilitate`

## Problem

The current `facilitate` mode (`src/services/chat/agents/facilitate.py`) teaches a
chapter by **looping over every matched section**, emitting a `FacilitateDigest`
of discrete `blocks[]`. Concepts surface as `[[cN]]` pills that open a **static**
`ConceptModal` (corpus-only, no Wikipedia, no follow-up). The "+" side panel
(`TempChat.tsx`) is a **stub** that returns a canned string.

The user wants facilitate to become: **"teach me ONE section as a connected
story, and let me pull any concept into a side conversation that draws from my
books AND Wikipedia."**

## Goals

1. **Storytelling.** One section rendered as a connected narrative (hook →
   movements → takeaway), tutor-grade KaTeX prose quality.
2. **Concept → side chat.** A concept pill opens a parallel panel seeded with a
   brief corpus+Wikipedia explanation, with a "deepen" affordance to explore the
   concept further — bounded to that concept, never leaking into the main thread.
3. **Exactly one section per request** (today: loops all matched sections).
4. **Better book association** in scope resolution.
5. **Remade response card** with structured text, tutor mode as the layout clue.

## Non-Goals (YAGNI cut list)

- No seam validator / `seams.py` for facilitate (one section = no seams).
- No multi-segment / per-author draft fan-out (one source, one writer call).
- No new Wikipedia client — reuse `research.py:wiki_evidence`.
- No persisting the side-chat into the conversation message list (that *is* the
  leak we must prevent by construction).
- No general RAG chat in the side panel (constrained concept explorer only).
- No in-place reshape of `FacilitateDigest` (add new type + discriminator; the
  `QAAnswer`/`ExtensionDigest` precedent).
- No keeping the looping `run_facilitate` on the new path (legacy-replay only).
- No reuse of `TempChat`'s stub reply logic (fork its shell/CSS only).
- No KG (`kg.py`) expansion.

## Design

### Reframe vs tutor

With **one** section there is exactly one block, so the story is one narrative —
but it must **not clone tutor**. Tutor weaves across multiple sources and needs
seam-validation because it stitches independently-drafted segments. Facilitate
over a single section has one source and no seams. We take tutor's **card layout
and KaTeX prose quality**, not its multi-segment draft+seam pipeline.

### Pipeline — new `run_facilitate_story` (single section)

```
resolve_section   (LLM resolve  → PURE-CODE section pick, closest-match+confirm)
  → fetch_section            (one Source; filter fetch_chapter_sections to the chosen section_id)
  → map_concepts             (LLM: ≤5 concepts + [[cN]] candidates)        ┐
  → concept_support ×N       (PURE CODE: fetch_concept_support, gather)    ┤ asyncio.gather
  → story_writer             (LLM: hook / movements[] / takeaway + [[cN]])
  → concept_binder           (PURE CODE: build ConceptAnchor provenance + StoryCitation
                              VERBATIM from support payloads; strip [[cN]] with no support)
  → verify                   (LLM, ONE bounded retry: grounding + proofread)
  → FacilitateStory
```

Mostly `asyncio.gather`. Fail-open: wiki/retrieval errors degrade locally, never
abort. The old `run_facilitate` stays only for legacy-conv replay.

### Trust placement

- **LLM owns:** concept extraction, narrative prose, the verify verdict, the
  ≤2-sentence concept brief. Errors here are cheap and reviewable.
- **Pure code owns:** section selection, concept provenance, citation
  construction, `[[cN]]` validity. The writer's draft schema has **no provenance
  field and no citation field** — it can only emit `[[cN]]` tokens. The binder
  copies `book/section/pages` verbatim from the retrieval payload. A `[[cN]]`
  with no backing support is **stripped from the prose** (marker removed, text
  kept) — same move as `qa_bind`.

### Formal statements — reproduce verbatim, then unpack didactically

Statistical sections carry **formal statements** (definitions, lemmas, theorems,
propositions, corollaries). For these the response must:

1. **Reproduce the statement EXACTLY** as it appears in the source (math in
   `$$…$$`) — never paraphrase a theorem.
2. Immediately **below**, explain it didactically in a fixed four-part arc:
   **elements** (name each symbol/term, especially the formulas) → **associations**
   (how the elements relate / what acts on what) → **intuition** (what it means in
   plain words, why it holds) → a **concise closing** line (the one-sentence
   takeaway of the statement).

A `movement` is therefore **either a prose paragraph or a formal block**. Prose
movements carry the narrative; formal movements carry a verbatim statement + its
unpacking. The writer chooses, per movement, which one a piece of the section is.

**Verbatim fidelity (enforcement):** "reproduce exactly" cannot be fully
guaranteed against OCR'd source by an LLM alone, so it sits on two rungs —
(a) prompt instructs verbatim copy; (b) a **pure-code fidelity check** in
`verify` normalises whitespace/LaTeX-delimiters and fuzzy-matches each
`formal.statement` against the source section text; below threshold →
`grounding.ok=false` with the statement listed in `unsupported` (fabricated /
materially-altered statement is caught, not silently shipped). The verify LLM may
repair LaTeX delimiters in a statement but is told **not to alter its meaning**.

### Schemas (`src/services/chat/schemas/output.py`)

```python
class FormalStatement(BaseModel):
    kind: Literal["definition", "lemma", "theorem", "proposition",
                  "corollary", "remark"]
    statement: str       # reproduced VERBATIM from source; display math in $$…$$
    explanation: str     # didactic arc: elements (esp. formulas) → associations
                         # → intuition → concise close. May carry [[cN]].

class Movement(BaseModel):
    """Exactly one of `prose` / `formal` is populated."""
    prose: str = ""                          # narrative paragraph (may carry [[cN]])
    formal: FormalStatement | None = None    # present iff this is a formal movement

class FacilitateStoryDraft(BaseModel):
    """Writer structured output. NO citation/provenance field by design —
    the writer may ONLY emit [[cN]] markers referencing ids it was given."""
    hook: str                  # 1 paragraph — why this section matters, the through-line
    movements: list[Movement]  # 2–5 movements — the connected story (prose and/or formal)
    takeaway: str              # 1 paragraph — what the reader now understands
    math_blocks: list[str] = []

class FacilitateStory(BaseModel):
    mode: Literal["facilitate_story"]
    scope: ChapterScope                  # exactly one resolved section_id
    hook: str
    movements: list[Movement]
    takeaway: str
    concepts: list[ConceptAnchor] = []   # reuse existing; provenance built by code
    citations: list[StoryCitation] = []  # reuse research.py StoryCitation (📕 / 🌐)
    math_blocks: list[str] = []
    grounding: dict = {}
```

`ChapterScope` gains a `section_id` field (one resolved section). Discriminator on
`mode` keeps legacy `FacilitateDigest` convs rendering via the old card.

The exactly-one-of `prose`/`formal` rule is a model validator on `Movement`
(true-by-construction; a movement can never be both empty and both populated).

### Concept → side chat

New endpoint, **separate** from `/api/chat`:

```
POST /api/concept/explore
  body: { term, kind, book_slug, section_id, conversationId, history?: [{role,text}] }
  → SSE: brief seed (no history)  OR  a "deepen" follow-up answer (with history)
```

- **Seed (no history):** one pure-code-orchestrated pass —
  `corpus_evidence(term, …) ∥ wiki_evidence(term, …)` via `asyncio.gather`, then a
  single LLM "brief" call (≤2 sentences) given both evidences. The LLM **cannot
  author the citation chips** — those are `_citation(e)` from `research.py`,
  verbatim. Seed bubble = LLM prose + 📕/🌐 chips bound by code.
- **Deepen / follow-up (with history):** the same `research.py` retrieval scoped
  to `term` + the follow-up, re-run, fresh brief. A **bounded concept explorer**,
  not an open chat: every turn re-grounds on corpus+wiki for `term (+ follow-up)`.
- **Stateless w.r.t. the conversation.** The endpoint never reads or writes the
  conversation's message list. This is the structural guarantee that the
  side-chat cannot leak into the main answer.

### Frontend

- **`FacilitateStoryCard.tsx`** — tutor-grade layout: hook / movements / takeaway
  regions, KaTeX, `[[cN]]` → concept pills, 📕/🌐 citation chips. Renders
  `FacilitateStory`. Legacy `FacilitateDigest` still routes to the old card via
  discriminator.
- **`ConceptChat.tsx`** — fork `TempChat`'s shell/CSS, new logic. Pill click opens
  it next to the answer; seed bubble + "deepen" follow-up call
  `/api/concept/explore`. **Never calls the main `setMessages`** (isolation test
  enforces).

### Book / section resolve (`src/services/chat/agents/_scope.py`)

Extend `resolve_book` → `{book, chapter, section_id}`:

- **Explicit section number** present (e.g. `7.4`) → resolve deterministically via
  the existing `expand_section_refs`; skip confirm if book confident.
- **No section number** → match the requested subtopic to the chapter's real h2
  headings (reuse the Extension word-boundary matcher,
  `extension_agents/runner.py:_extract_section_num` + section-match helper),
  take top-1; if score below floor OR the book is ambiguous → emit a `clarify`
  event with candidate book+section list (extend existing `maybe_clarify`).
- **Better book association:** richer catalog weighting (authors_short / field) in
  `CHAPTER_PARSE_PROMPT`; the lift is mostly the confirm gate, not the prompt.

The exact h2-match score floor (confirm vs proceed) is **data-dependent** — to be
calibrated against ~10 real queries on the live catalog during live-verify, not
locked blindly in the spec.

## Enforcement ladder (true-by-construction)

| Invariant | Rung | Mechanism |
|---|---|---|
| Exactly ONE section per request | schema + code | `ChapterScope.section_id`; runner iterates a single `Source`, no list |
| Citations / provenance verbatim | schema + code | writer schema has no citation field; pure-code `concept_binder`; property test: every rendered provenance ∈ some support payload |
| Side-chat can't leak to main thread | schema + code | separate endpoint + response type; never persisted to message list; isolation test that the handler never writes the conversation store and the panel never calls `setMessages` |
| Writer can't invent concepts | schema + prompt + code | writer GIVEN `cN=term` list; binder strips unknown `[[cN]]` |
| Formal statement reproduced verbatim | prompt + code | writer told to copy verbatim; `verify` fuzzy-matches each `formal.statement` vs source → degraded grounding if altered/fabricated |
| Movement is prose XOR formal | schema | `Movement` model validator: exactly one of `prose`/`formal` populated |

## Failure-mode map

| Failure | Local degradation | Visible as |
|---|---|---|
| Wiki latency / 403 / miss | `wiki_evidence` returns `[]` (fail-soft); seed uses corpus only | no 🌐 chip; brief is corpus-only |
| nano hallucinates the brief | chips remain verbatim (pure code); prose may drift | grounding verdict; chips show real provenance |
| Writer invents `[[c9]]` | binder strips marker, keeps prose | marker gone; concept list shows only bound concepts |
| Single section too thin for a narrative | `concept_support` pulls cross-section/cross-book support (same-author-first); writer told to anchor to neighbouring concepts | fewer movements; takeaway still present; no abort |
| Concept-pill density | cap `_MAX_CONCEPTS` (5); binder dedupes | unbound terms render as plain text |
| Verify fails | ONE bounded retry, then keep draft + `grounding.ok=false` | grounding chip degraded; no loop |
| Formal statement altered/fabricated | pure-code fidelity check flags it; statement still rendered but grounding degraded | grounding chip degraded; statement listed in `unsupported` |
| Section has no formal statement | `movements` are all prose; renderer shows no statement blocks | normal narrative, no formal block |
| Section resolve ambiguous | `clarify` event with candidates | user picks book+section; no wrong-section answer |
| Side-chat scope creep | endpoint re-grounds every turn on `term`; no main-thread tools | answers stay concept-scoped |

## Reversal evidence (assumptions that could flip the design)

- `ConceptAnchor.provenance` is single-source. If a concept routinely needs 2+
  sources, switch provenance to a list **before** the binder task.
- nano adequacy for narrative+brief (2026-06-03 sweep says yes). If 3-run variance
  shows incoherence, fix the **prompt through-line**, escalate model only if the
  prompt fails.
- Side-chat needs no memory beyond the current term thread. If users expect it to
  remember earlier concepts, add a per-term `concept_threads` side table — still
  never the main message list.
- `fetch_chapter_sections` can be filtered to one section by `section_id`. If not,
  add a small `fetch_section(book, chapter, section_id)` helper.

## Decomposition — 9 bite-sized TDD tasks

1. **Schemas** — `FacilitateStoryDraft` + `FacilitateStory`; `ChapterScope.section_id`;
   discriminator wiring (legacy `FacilitateDigest` still renders). Tests: writer
   schema has no citation/provenance field; round-trip; discriminator routes.
2. **Section resolve** — extend `_scope.resolve_book` → `{book, chapter, section_id}`;
   closest-match-and-confirm; reuse Extension word-boundary matcher; richer
   catalog weighting in `CHAPTER_PARSE_PROMPT`. Tests: explicit `7.4` deterministic;
   low-confidence book → `clarify`; no-section → top-1 heading.
3. **Concept binder (pure code)** — build `ConceptAnchor.provenance` + `StoryCitation`
   verbatim from support payloads; strip unbound `[[cN]]`. Property test: every
   rendered provenance ∈ some payload; invented marker stripped.
4. **Facilitate-story runner** — `run_facilitate_story` (single section, gather:
   map→support→write→bind→verify, one bounded retry). Includes the pure-code
   **formal-statement fidelity check** (normalise + fuzzy-match each
   `formal.statement` vs source; degrade grounding if altered). Tests: exactly one
   block; fail-open on wiki/retrieve; bounded retry; altered statement → degraded
   grounding; verbatim statement → ok.
5. **Prompts** — `FACILITATE_STORY_WRITE` (hook / movements / takeaway,
   through-line, `[[cN]]` only from given ids, no `#`/`##` headings; **formal
   movements: reproduce the statement VERBATIM in `formal.statement` with display
   math in `$$…$$`, then unpack it in `formal.explanation` as elements → associations
   → intuition → concise close**), `FACILITATE_BRIEF` (≤2-sentence concept seed);
   extend `FACILITATE_VERIFY` to repair statement LaTeX without changing meaning.
   Tests: prompt schema enforced; formal movement round-trips.
6. **Concept-explore endpoint** — `POST /api/concept/explore` SSE; seed via
   `research.py` (corpus ∥ wiki gather + brief LLM); stateless re: conversation.
   Tests: chips = pure-code `_citation`; handler never writes the conversation
   store (isolation test).
7. **Frontend response card** — `FacilitateStoryCard` (hook / movements / takeaway,
   KaTeX, 📕/🌐 chips, `[[cN]]` → pills). A **formal movement** renders as a styled
   statement block (kind badge — Definition / Lemma / Theorem… — + verbatim
   statement in a quote/callout with display math) followed by its didactic
   `explanation` underneath; prose movements render as paragraphs. Tests: renders
   three regions; prose vs formal movement render distinctly; statement block shows
   kind badge + KaTeX; pill click fires concept-open.
8. **Frontend ConceptChat panel** — fork TempChat shell; wire pill → panel; seed
   bubble + "deepen" follow-up to `/api/concept/explore`; never calls main
   `setMessages`. Tests: panel state isolated from thread; deepen re-queries.
9. **Docs / modal lockstep** — `web/src/data/facilitate*` (`facilitateMode.ts` /
   pipeline data) + `FacilitatePipelineDiagram.tsx` new stages; markdown
   `docs/services/chat-features/53-facilitate-concept-map.md`; HTML
   `docs/common ground/Elements/modes/facilitate.html`; `docs/system/invariants.md`
   + `docs/system/changelog.md`. (Dual-surface + modal-fidelity rule.)

## Repo anchors

- Pipeline: `src/services/chat/agents/facilitate.py`
- Reuse: `src/services/chat/research.py` (`corpus_evidence` / `wiki_evidence` /
  `_citation`, `StoryCitation`)
- Resolve: `src/services/chat/agents/_scope.py` (`resolve_book`,
  `expand_section_refs`, `maybe_clarify`, `_BOOK_CONFIRM_CUTOFF`)
- Section fetch: `src/services/chat/retrieval.py` (`fetch_chapter_sections`,
  `fetch_concept_support`, `_section_order_in_book`)
- Word-boundary matcher: `src/services/chat/agents/extension_agents/runner.py`
- Schemas: `src/services/chat/schemas/output.py`
  (`ConceptAnchor`, `ConceptProvenance`, `StoryCitation`, `QAStoryAnswer` precedent)
- Endpoint: `src/services/chat/api.py`
- Frontend: `web/src/components/{FacilitateDigestCard,FacilitateContent,ConceptModal,TempChat}.tsx`
- Strongest reference implementation: the QA-story pipeline (anti-tutor schema +
  discriminator + pure-code `qa_bind` citation binding).
