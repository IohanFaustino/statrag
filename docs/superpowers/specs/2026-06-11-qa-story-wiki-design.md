# Q&A Rebuild — Storytelling Voice + Wikipedia Grounding (Design)

**Date:** 2026-06-11
**Status:** Design — awaiting user approval (plan gate)
**Author:** orchestrator_Agent, with fable creative-advisor counsel folded in.
**Supersedes / reframes:**
- the shipped flat Q&A (`scope → retrieve → generate → verify`, `QAAnswer{text}`) in
  [`docs/services/chat-features/51-qa-mode.md`](../../services/chat-features/51-qa-mode.md);
- **partially retires** the agentic-roster redesign
  [`2026-06-05-qa-deepagent-design.md`](2026-06-05-qa-deepagent-design.md) (rev 2026-06-08) —
  see §0.1 for what is kept vs cut and the branch-reconciliation decision.

**Driving goal (user, verbatim intent):** Q&A answers ONE precise question grounded in
several sources. ADD (1) **Wikipedia search** to augment corpus retrieval (borrow Extension
mode's pure-code wiki fetch + verbatim citation binder), and (2) a **storytelling voice** that
still holds a clear **introduction → deepening → concise conclusion** structure — while
preserving the hard guarantee that Q&A is *structurally incapable of becoming the tutor*.

---

## 0. Creative-advisor verdict (folded in)

> Storytelling is a **register** (voice); the tutor is a **topology** (open-ended
> sections/aspects/figures/coverage). As long as the answer schema cannot grow sections and
> the pipeline has no figure/aspect/coverage stages, narrative voice cannot drift into
> teaching. The intro→deepening→conclusion arc is *sufficient* structure for storytelling.
> Borrow Extension's evidence/binder trust partition wholesale; bind to flowing prose via
> inline `[[eid]]` marker tokens that a **pure-code binder** rewrites to numbered `[n]` markers
> + verbatim `StoryCitation`s. The prior agentic decompose→subagent→checker machinery is
> **YAGNI** for wiki+voice — the pipeline stays flat.

Key adopted decisions: flat pipeline (no deepagents); writer schema has **no citation field**
(cannot author sources); answer schema has **exactly three fixed string fields** (cannot grow
sections); pure-code binder is the trust boundary; ≤3 bounded wiki fetches via `gather`, no
LLM gate deciding "should I consult wiki"; reuse `StoryCitation` 📕/🌐 chips; **do not drop
narrative sentences** on unbound markers (strip the marker, keep prose — dropping mid-narrative
breaks the arc; uncited-claim policing is verify's advisory job).

### 0.1 What is kept vs cut from the 2026-06-08 agentic-roster design

| Element of the roster design | Disposition | Why |
|---|---|---|
| `QAAnswer{thesis, body, conclusion}` 3-field anti-tutor progression | **KEPT, renamed** → `QAStoryAnswer{intro, deepening, conclusion}` | The fixed-3-field anti-tutor guarantee is exactly right; storytelling just changes the register and the field names. |
| Open Agent Skills `SKILL.md` + `AGENTS.md` roster (scope/orchestrator/analyst/checker) | **CUT** | Needs zero search loops/subagents for wiki+voice. YAGNI. |
| `deepagents` orchestrator, `StoreBackend /sources/`, `search_corpus` tool loop | **CUT** | Flat `asyncio.gather` over corpus + ≤3 wiki fetches buys all the parallelism needed. |
| adaptive simple/compound gate, analyst subagents, `QAFinding` | **CUT** | One gap → one writer call. The miner/fan-out exists in Extension only because it has a timeline. |
| checker re-call loop (`QA_MAX_RECHECK`), `QACheck` | **CUT → reduced** to advisory `verify` + **one** bounded zero-marker redraft. |
| hard tutor-isolation guarantee | **KEPT and strengthened** (schema + pipeline, see §3). |
| deterministic fallback (never regress) | **KEPT** (§7). |

**BRANCH-RECONCILIATION (open decision — user must settle, see §12):** three unmerged
`feat/qa-deepagent*` branches exist in worktrees (built per memory, never merged into
`feat/component-equation-enforcement`). This spec's recommended base is **extend the shipped
flat Q&A on the current branch** (the agentic branches implement the now-cut roster). The
binder/3-field-schema/refusal-list in this spec are reusable even if the user instead wants the
roster branch as the base.

---

## 1. The anti-tutor refusal list (true-by-construction)

The line, stated once: **tutor = breadth** (many subtopics, figures, coverage guarantees);
**Q&A = depth on one gap with a rhetorical arc.** Each refusal is enforced at the strongest
available rung of the ladder (schema > pure code > test > prompt):

| Tutor behaviour | Q&A refusal | Enforced at |
|---|---|---|
| Open-ended sections / aspects | Exactly 3 fixed **string** fields (`intro`/`deepening`/`conclusion`) | **Schema** (no `list[Section]`, ever) |
| Figures / image retrieval | No figure stage, no figure field | **Schema + pipeline** (stage does not exist) |
| Breadth/coverage across subtopics | One `target_gap`; no coverage-check stage | **Pipeline + scope** |
| Unbounded length | Paragraph caps (intro 1 / deepening ≤3 / conclusion 1) + token cap | **Pure code** |
| Headings / scaffolding (`## Overview`) | Markdown headings (`^#{1,6} `) stripped from the 3 fields | **Pure code** |
| Pedagogical apparatus (exercises, "in the next section…") | Conclusion must close, not open | **Prompt + verify advisory flag** |
| Re-teaching prerequisites | `assumed_known` exclusion | **Prompt** (existing) |
| Model-authored citations (lie channel) | Writer schema has **no** citations field | **Schema + pure-code binder** |

A property test asserts the serialized `QAStoryAnswer` JSON contains **no** `sections` /
`aspects` / `figures` keys and **no** markdown headings in the 3 prose fields (§9, T2/T4).

---

## 2. Architecture — flat, deterministic, no graph framework

```
scope (LLM nano, extended: + wiki_terms)
  → QAScope{ target_gap, assumed_known, answer_form, wiki_terms[] }
  │
  → retrieve (PURE CODE, asyncio.gather):
  │     corpus_evidence(target_gap)            → Evidence[kind=corpus]   (verbatim meta)
  │     wiki_evidence(target_gap)              → Evidence[kind=wikipedia] (verbatim meta)
  │     wiki_evidence(t) for t in wiki_terms[:2]
  │     ⇒ evidence: list[Evidence]  (each carries a stable .id)
  │
  → write (LLM, ONE call):
  │     storytelling intro→deepening→conclusion prose with inline [[eid]] tokens
  │     → QAStoryDraft{ intro, deepening, conclusion, math_blocks }   (NO citation field)
  │
  → bind (PURE CODE): qa_bind(draft, evidence)
  │     scan the 3 fields for [[eid]] tokens; valid id → rewrite to [n] (first-appearance
  │     numbering, shared across the 3 fields) + append a StoryCitation built VERBATIM from
  │     Evidence.meta. invalid id → strip token, keep prose, count grounding["unbound_markers"].
  │     strip headings; enforce paragraph caps; mid-line $$ normalization.
  │     zero markers bound ⇒ ONE bounded redraft with explicit cite instruction, ship 2nd regardless.
  │
  → verify (LLM nano, advisory): soften/flag unsupported claims; never aborts. → grounding{}
  │
  → QAStoryAnswer{ intro, deepening, conclusion, scope, citations[], math_blocks[], grounding }
```

Two LLM authoring stages (scope, write) + one advisory LLM stage (verify). Everything else is
pure code. No `deepagents`, no `StoreBackend`, no subagents.

### 2.1 Isolation from tutor mode (hard constraint)

Rebuilding Q&A must not change a single tutor file, and Q&A must not import tutor
logic/prompts/skills. `deep_tutor.py`, `orchestrator_workers.py`, `ow_deepagents.py`,
`prompts/deep_tutor.py`, `ow_skills/` — **never imported**. Enforced by isolation grep (§9 T8).
Shared read-only primitives only: the new `research.py` (extracted from extension_agents) and
the `StoryCitation` render helpers.

---

## 3. Shared module extraction (Chinese wall is *between services*, not intra-chat)

The wiki + binder machinery currently lives in `src/services/chat/agents/extension_agents/`.
Both Extension and Q&A are inside the **same service** (`src/services/chat/`), so sharing is
wall-compliant. Extract the pure-code, mode-agnostic pieces into a shared module:

`src/services/chat/research.py` (NEW) — moves verbatim:
- `Evidence` dataclass (`subject_id`, `kind`, `text`, `meta`, `id`)
- `corpus_evidence(...)`, `wiki_evidence(...)`, `_wiki_summary_json(...)`, `_WIKI_*` constants
- `_citation(Evidence) -> StoryCitation` + `_label(Evidence)` (the verbatim-meta → citation map)

`extension_agents/research.py` and `binder.py` re-import from `research.py` (thin shims) so
Extension's tests stay green and behaviour is byte-identical. Q&A imports the same functions.

> **`subject_id` note:** the field name is Extension-flavoured. Q&A passes a constant
> `subject_id="qa"` (single gap, no timeline). Keep the field for byte-identical Extension
> behaviour; it is harmless for Q&A.

---

## 4. Schemas (`src/services/chat/schemas/output.py`)

```python
class QAScope(BaseModel):                         # EXTENDED
    target_gap: str
    assumed_known: list[str] = Field(default_factory=list)
    answer_form: Literal["explanation","definition","comparison",
                         "derivation","yes_no","list"] = "explanation"
    wiki_terms: list[str] = Field(default_factory=list)   # NEW — ≤2 named entities/eponyms

class QAStoryDraft(BaseModel):                    # NEW — writer structured output, NO citations
    intro: str          # ≤1 paragraph; hook the question
    deepening: str      # ≤3 paragraphs; the answer, [[eid]] tokens inline
    conclusion: str     # ≤1 paragraph; close, no "next steps"
    math_blocks: list[str] = Field(default_factory=list)

class QAStoryAnswer(BaseModel):                   # NEW — final answer; REPLACES QAAnswer path
    intro: str
    deepening: str
    conclusion: str                               # exactly 3 content fields — no list[Section] EVER
    scope: QAScope
    citations: list[StoryCitation] = Field(default_factory=list)   # REUSE — corpus 📕 / wiki 🌐
    math_blocks: list[str] = Field(default_factory=list)
    grounding: dict = Field(default_factory=dict) # verify verdict + binder diagnostics
```

`QAStoryAnswer` reuses `StoryCitation` (kind `corpus`|`wikipedia`, verbatim fields). The writer's
`QAStoryDraft` deliberately has **no** citations field — it cannot author sources. Re-export
`QAStoryDraft`, `QAStoryAnswer` from `schemas/__init__.py`. The legacy `QAAnswer`/`QAGenerateOut`/
`QAVerifyOut` are removed from the Q&A path (kept only if a legacy-conversation renderer needs
the old shape — see §10 discriminator).

**`grounding` keys:** `{ok: bool, unsupported: list[str], confidence: float, unbound_markers:
int, corpus_weak: bool, wiki_unavailable: bool, lints: list[str]}`.

---

## 5. The pure-code binder — `qa_bind` (the trust boundary)

`src/services/chat/agents/qa.py::qa_bind(draft: QAStoryDraft, evidence: list[Evidence])
-> QAStoryAnswer`:

1. Build `by_id = {e.id: e for e in evidence}`.
2. Walk `intro`, then `deepening`, then `conclusion` in order; regex-find `[[<eid>]]` tokens.
3. First time a **valid** eid appears → assign the next integer `n` (shared sequence across all
   3 fields), append `_citation(by_id[eid])` (verbatim `StoryCitation`) to `citations`, rewrite
   the token to `[n]`. Repeat valid eid → reuse its `n`.
4. **Invalid** eid (not in `by_id`) → strip the token, leave surrounding prose intact, increment
   `grounding["unbound_markers"]`. **Never drop a sentence.**
5. Strip markdown headings (`^#{1,6}\s` lines) from each field; enforce paragraph caps
   (intro 1 / deepening ≤3 / conclusion 1) by flagged truncation → `grounding["lints"]`.
6. Apply the existing mid-line `$$`→`$` normalization (`_inline_midline_display` analogue) so
   display math renders (see memory: tutorview-midline-display-math).
7. If `len(citations) == 0` after binding (writer emitted zero/all-invalid markers) → caller
   triggers **one** bounded redraft; ship the second attempt regardless and set
   `grounding["ok"]=False` if still uncited.

**Property invariants (tested):** every field of every emitted `StoryCitation` exists verbatim
in some `Evidence.meta`; every `[n]` in prose maps to `citations[n-1]`; no headings remain.

---

## 6. Wikipedia retrieval strategy (bounded, deterministic)

- **Always** one `wiki_evidence(target_gap)`.
- **Plus** one per `scope.wiki_terms` entry, **capped at 2** → max **3** wiki fetches.
- All wiki fetches + corpus retrieval run in **one** `asyncio.gather` (`wiki_evidence` is sync →
  `asyncio.to_thread`). No LLM gate decides whether to consult wiki; no loop.
- Corpus remains the **primary authority**. The writer prompt frames wiki as context / history /
  intuition / naming ("the textbooks define X `[[c1]]`; the inequality is named for Chebyshev
  `[[w1]]`"). Wiki never silently substitutes for missing corpus: if corpus retrieval is weak/
  empty, set `grounding["corpus_weak"]=True` and the prose says so.
- Wiki fetch error/timeout → proceed corpus-only, `grounding["wiki_unavailable"]=True`.

---

## 7. Error handling & degradation (bounded loops only — at most ONE redraft total)

| Failure | Degradation | Visibility |
|---|---|---|
| Scope parse fail | fail-open: whole query as `target_gap`, `wiki_terms=[]` | — |
| Wiki fetch error/timeout | proceed corpus-only | `grounding["wiki_unavailable"]=True` |
| Corpus empty, wiki has hits | answer from wiki, prefixed "not covered in your textbooks" | `grounding["corpus_weak"]=True` |
| Both empty | short honest "cannot answer from available sources" in the 3-field shape, `citations=[]` | `grounding["ok"]=False` |
| Writer emits invalid `[[eid]]` | token stripped, prose intact | `grounding["unbound_markers"]=n` |
| Writer emits zero bound markers | ONE redraft w/ explicit cite instruction; ship 2nd regardless | `grounding["ok"]=False` if still uncited |
| Headings / over-cap prose | pure-code strip + flagged truncation (no redraft) | `grounding["lints"]=[…]` |
| Writer LLM exception | **deterministic fallback**: corpus-only nano generate into `{intro,deepening,conclusion}` (regression-safety, never below current behaviour) | logged |
| Verify exception | treat as advisory pass, low confidence | fail-open |

SSE stream always terminates in `done`.

---

## 8. SSE contract & models

Terminal contract (frontend keys off `schema`):
```
meta → [progress…] → structured_output{schema:"QAStoryAnswer"} → sources_full → retrieval_meta → usage → done
```
Progress events (advisory): `progress{stage:"retrieving"}`, `progress{stage:"writing"}`,
`progress{stage:"binding"}`, `progress{stage:"redraft"}` (only when a redraft fires).

`sources_full` carries the corpus `Source` rows (unchanged shape) so the existing sources panel
still works; wiki evidence surfaces only as `StoryCitation` chips in the card (no `Source` row,
matching Extension).

**Models:** nano default for scope, write, verify. `stageModels` overrides per stage (keys:
`scope`, `write`, `verify`). Env: `QA_SCOPE_MODEL` / `QA_WRITE_MODEL` / `QA_VERIFY_MODEL`.

### Env flags

| Flag | Default | Meaning |
|---|---|---|
| `QA_TOP_K` | `4` | corpus hits |
| `QA_WIKI_TERMS_MAX` | `2` | extra wiki lookups beyond target_gap |
| `QA_SCOPE` | `1` | enable scope pre-pass |
| `QA_VERIFY` | `1` | enable advisory verify |
| `QA_WIKI` | `1` | enable wiki augmentation (0 = corpus-only) |
| `QA_SCOPE_MODEL`/`QA_WRITE_MODEL`/`QA_VERIFY_MODEL` | nano | per-stage overrides |

`"qa"` stays in `settings.use_v2_modes`.

---

## 9. Frontend (lockstep — dual surface + modal)

| Surface | Change |
|---|---|
| `web/src/types.ts` | `QAScope += wiki_terms`; add `QAStoryAnswer{intro,deepening,conclusion,scope,citations(StoryCitation[]),math_blocks,grounding}`; reuse existing `StoryCitation` TS type |
| `QAAnswerCard.tsx` | render intro (lead) → deepening (prose, `renderInlineWithCites` + `MathBlock`) → conclusion; **corpus 📕 / wiki 🌐 `StoryCitation` chips** (borrow from `StoryDigestCard.tsx`); grounding badge; "answered with N corpus + M wikipedia sources" hint |
| `qaPipeline.ts` + `QAPipelineDiagram.tsx` | reshape nodes: `scope → retrieve(corpus∥wiki) → write → bind → verify`; bind is a **pure-code** node (no model dropdown); per-LLM-stage dropdowns on scope/write/verify |
| `MessageThread.tsx` | handle `progress` (retrieving/writing/binding/redraft); branch `schema==="QAStoryAnswer"` → `<QAAnswerCard>`; legacy `QAAnswer` discriminator → legacy render path |
| `QAModeModal.tsx` / `qaMode.ts` | copy → storytelling + wiki pipeline |
| **HTML doc** `docs/common ground/Elements/modes/qa.html` | both Q&A diagrams updated to the new flat pipeline (dual-surface rule) |

After the diagram change: open the Q&A `(i)` modal on `:5175` and confirm it matches
`docs/common ground/Elements/modes/qa.html`.

---

## 10. Legacy conversations

Existing `QAAnswer{text}` conversations must still render. Frontend keeps a discriminator: a
stored payload with `text` → legacy renderer; with `intro`/`deepening`/`conclusion` →
`QAStoryAnswer` renderer (mirrors the Extension v1/v2 card split).

---

## 11. Lockstep artifacts checklist

| Aspect | Path |
|---|---|
| Shared wiki+binder | `src/services/chat/research.py` (NEW) + extension shims |
| Agent logic (rebuilt) | `src/services/chat/agents/qa.py` (`retrieve`, `write`, `qa_bind`, `verify`, `run_qa`, fallback) |
| Prompts | `src/services/chat/prompts/qa.py` (`QA_SCOPE_PROMPT`+wiki_terms, `QA_STORY_WRITE_PROMPT`, `QA_VERIFY_PROMPT`, `QA_FALLBACK_PROMPT`) |
| Schemas | `src/services/chat/schemas/output.py` (+ `__init__` re-export) |
| Mode id / dispatch | `_core.py`, `modes.py`, `router.py` — **no change** (regression test only) |
| Cost | `src/services/chat/cost.py` (new stage keys if metered) |
| Frontend | `types.ts`, `QAAnswerCard.tsx`, `qaPipeline.ts`, `QAPipelineDiagram.tsx`, `MessageThread.tsx`, `qaMode.ts`, `QAModeModal.tsx` |
| HTML doc (dual surface) | `docs/common ground/Elements/modes/qa.html` |
| Markdown docs | `docs/services/chat-features/51-qa-mode.md` (rewrite), `docs/services/chat.md` |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| Tests | per the plan |

---

## 12. Open decisions for the user (plan gate)

1. **Branch base** *(must settle before execution)* — recommended: **extend the shipped flat
   Q&A** on `feat/component-equation-enforcement` (this spec). Alternative: the user may want one
   of the unmerged `feat/qa-deepagent*` worktree branches as the base — but those implement the
   roster machinery this spec deliberately cuts, so that would be a different (heavier) feature.
2. **Wikipedia primacy** — confirmed corpus-primary, wiki = context/history/naming. OK?
3. **Storytelling strength** — intro→deepening→conclusion + narrative register, headings
   forbidden, length-capped. Acceptable as the anti-tutor line, or does the user want even
   tighter caps (e.g. deepening ≤2 paragraphs)?
4. **`QAStoryAnswer` is a breaking payload change.** Plan keeps a legacy discriminator for old
   convs (§10). Confirm that's enough (vs migrating old convs).

---

## 13. Future / deferred (YAGNI now)

- Per-paragraph evidence lists instead of inline `[[eid]]` (advisor Alternative 1) — only if
  live runs show nano garbling markers >~10%.
- Agentic decompose/checker roster (the cut 2026-06-08 design) — only if compound-question
  retrieval quality becomes the priority; the binder + 3-field schema graft onto it unchanged.
- Wiki full-extract (beyond REST summary) — only if summaries prove too thin to cite.
- Wiki caching/rate-limiting — ≤3 fetches/question; a timeout suffices.
