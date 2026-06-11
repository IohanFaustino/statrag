# Tutor Narrative Rebuild — Design

**Date:** 2026-06-11
**Branch base:** `feat/component-equation-enforcement`
**Status:** approved (user), pre-plan
**Advisor counsel:** creative_Advisor (fable) — enforcement ladder, failure-mode map, cut list folded in.

## Problem

The `tutor` chat mode has accreted **7 synthesis variants** (L0 single · L1/L2 orchestrator-workers · L3/L5/L6/L7 deepagents · `organize` long-context), selected by `tutorWorkflow` request knob + `TUTOR_OW_HARNESS` / `TUTOR_WORKFLOW` env flags. The answer renders as **6 disjoint aspect blocks** with no narrative connection between them — coherence is implicit (a `thesis` injected into the draft) but the sections read as independent encyclopedia entries.

Two goals:
1. **Collapse the 7 variants to ONE.**
2. **Thread the sections with a single continuous narrative** (storytelling that starts the discussion and transitions themes), with the **introduction (TL;DR) standalone, outside the thread.**

## Locked decisions

1. **Output = ONE continuous narrative arc.** Intro (TL;DR) standalone, outside the story.
2. **Collapse the synthesis tail only.** Keep the retrieval front unchanged. Delete orchestrator-workers, deepagents variants, `organize` long-context, harness levels, their env flags, and the `tutorWorkflow` request knob.
3. **Fixed 5-beat arc** after the intro: ① define ② formalize (auto-dropped when no theorem) ③ see-it-work ④ use-it ⑤ go-further. Storytelling lives in HOW beats are written + transitions, not WHICH beats appear.
4. **Transitions woven into prose** — no new schema field, no new frontend element. Each non-intro beat opens carrying the prior thread forward and closes setting up the next.
5. **Legacy invariants must not regress:** component equations verbatim/reconstructed in the relevant beat; `[N]` citation reconcile; figure placement into a target beat; `$$…$$` owns its line.
6. **Formula recovery is REWIRED, not deleted.** `formula_gaps.py` / `formula_recovery.py` / `formula_cache.py` are currently wired *inside* `run_orchestrator_workers` (gap-triggered vision read of dropped equations → `<recovered_equations>` fed verbatim into synth + global Qdrant cache). Deleting OW must **re-attach** this to the single narrative draft call — feed `<recovered_equations>` verbatim into the relevant beat. Dropping it would regress invariant (iv) and the shipped formula-recovery feature.

## Architecture

### Pipeline after the cut
```
concept → query-plan → retrieval → density/rerank → author-diversity
  → coverage → synthesis-plan{thesis, contrasts} → image-judge
  → ONE narrative draft call (single LLM pass, all 5 beats + intro)
  → pure-code post: midline-$$ fix → citation reconcile → figure place
  → pure-code SEAM VALIDATOR
  → (on fail) ONE silent non-streamed redraft → accept + record quality
  → assemble_markdown → SSE → frontend (unchanged)
```
Everything left of the narrative draft call is **untouched**.

### Beat → field mapping (NO renames — preserves streaming/assembly/figure code)
| Beat | Existing `DeepTutorAnswer` field | In thread? |
|---|---|---|
| Intro / TL;DR | `tldr` | **No** (standalone) |
| ① Define | `definition` | Yes |
| ② Formalize (auto-drop) | `formal_statement` (empty ⇒ heading dropped) | Yes, when present |
| ③ See it work | `example_intuition` | Yes |
| ④ Use it | `applications` | Yes |
| ⑤ Go further | `further_reading` | Yes |

## Enforcement ladder (true-by-construction where possible)

| Property | Rung | Mechanism |
|---|---|---|
| (i) intro outside the thread | **code (free)** | Thread defined over beats ①–⑤ only; no `tldr`→① seam exists. Prompt rule: beat ① must not reference back to the intro. |
| (ii) each beat carries prior thread + sets up next | **validation (code) + prompt** | (a) per-beat `Field` descriptions state the open/close bridge contract; (b) **seam check** (pure code): first sentence of beat k+1 shares ≥1 content-lemma (stopword-stripped, lowercased) with last sentence of beat k **OR** with `thesis`. |
| (iii) develops the plan's `thesis` | **code-injection + validation** | Code injects `plan.thesis` as the first user-message line under `<thesis>…</thesis>`. Validation: thesis lemma overlap with `tldr` + ≥2 beats → `quality["thesis_adherence"]`. Not a hard gate (overlap too noisy). |
| (iv) legacy per-beat rules | **already placed — do not move** | Component eqs: `model_validator` (schema). Citations / figures / `$$`-owns-line: code. New non-interference tests only. |

### New module — `src/services/chat/agents/seams.py` (pure code, zero LLM)
- sentence extraction (first / last of each present beat)
- content-lemma overlap (stopword-stripped, lowercased — reuse the figure token-overlap idiom)
- boilerplate guard: reject if ≥2 beats open with same leading 3-gram, or opener hits a small canned-phrase blocklist ("Now that we…")
- **Polish/language-drift guard** (known long-run bug, finally structural): English stopword-ratio floor per beat
- **formalize-drop re-link**: when `formal_statement == ""`, the ②→③ seam is replaced by a ①→③ seam; ③ opener must not contain theorem/formal lexemes
- returns: pass/fail per seam + `quality` scores (`seam_continuity`, `lang_ok`, `thesis_adherence`)

### Single call + one bounded redraft (no LLM judge)
One context is the coherence mechanism (all beats in one attention window — a chain quintuples calls and rebuilds the orchestrator-workers blast radius we are deleting). On seam failure → **ONE silent, non-streamed** redraft, failing seams quoted verbatim in the retry message → on 2nd failure **accept + record** `quality["seam_continuity"] = fraction_passed`. Never aborts.

**⚠️ Load-bearing assumption (verify in build, Task 4):** `TutorView` treats the final `TutorAnswer` payload as authoritative (overwrites the streamed deltas). If true, the redraft is silent. If the stream is authoritative, either re-stream the redraft (worse UX) or move validation pre-stream (buffered draft, +latency). Verify before relying on silent redraft.

## Failure-mode map

| Failure | Guard (highest rung) | On trigger | Visibility |
|---|---|---|---|
| Beats degenerate into disconnected entries | seam check | 1 silent redraft (quoted seams) → accept | `quality["seam_continuity"]` |
| Polish/language drift | English stopword-ratio floor (code) | 1 redraft, "respond in English" prepended | `quality["lang_ok"]` |
| Equations swallowed into transition prose | existing `_inline_midline_display` + component-eq validator; new test: seam sentences contain no `$$` | validator raise → existing structured-output retry | pydantic error |
| Formulaic "Now that we…" boilerplate | 3-gram dedupe + blocklist; prompt offers 3 varied bridge techniques | seam failure → same redraft | `quality["seam_continuity"]` |
| Thesis ignored | code-injected `<thesis>` + overlap score | none (don't gate — too noisy) | `quality["thesis_adherence"]` |
| Formalize auto-drop orphans a transition | conditional ②→③ → ①→③ re-link; ③ opener theorem-lexeme blocklist | seam failure → redraft | `quality["seam_continuity"]` |
| Planner thesis empty/garbage | best-effort skip (coverage.py contract) | thread validation degrades to seam-only | log |
| Redraft also fails | hard bound: ONE retry, then accept | ship with low scores | `quality` dict |

## Cut list (YAGNI — do NOT build)
- LLM coherence judge / critic loop (`_ENABLE_CRITIQUE` stays off)
- per-beat chained generation or default narrative-editor 2nd pass
- embedding-cosine seam scorer (lexical overlap catches the failure class)
- any new env flag for narrative mode (it IS the path)
- frontend work (assemble_markdown already emits `## H2`; transitions live in section bodies)
- `SynthesisPlan.tasks` population (orchestrator-only — strip from `SYNTHESIS_PLAN_PROMPT`; keep schema field defaulting empty one release, then delete)
- a transitions schema field in the answer contract (renderer needs nothing)

## Model
Default stays the current cheap draft model (cost-first per project preference). Escalation ladder **only on measured evidence** (seam-fail >~30% after prompt tuning): hidden `thread: list[str]` generation field → stronger-model retry → weave editor pass. NOT built now; recorded as the reversal path.

## Lockstep surfaces (every pipeline change touches all)
- backend logic: `deep_tutor.py` (`_draft_coro` collapse), new `seams.py`
- prompts: `prompts/deep_tutor.py` (`DEEP_TUTOR_INSTRUCTIONS` narrative contract, per-beat `Field` descriptions, `<thesis>` injection, strip `tasks` from `SYNTHESIS_PLAN_PROMPT`)
- schemas: `schemas/output.py` (`Field` descriptions), `schemas/_core.py` (delete `tutorWorkflow`)
- env table: `docs/services/chat-features/36-deep-tutor.md`
- modal: `web/src/data/tutorPipeline.ts` + `web/src/components/PipelineDiagram.tsx` (delete OW/organize cluster nodes) + tests
- backend mermaid: `36-deep-tutor.md`
- per-feature doc: new `docs/services/chat-features/57-tutor-narrative.md` (+ supersede notes in 44/48/56)
- HTML: `docs/common ground/Elements/modes/tutor.html`
- invariants + changelog: `docs/system/invariants.md`, `docs/system/changelog.md`
- tests: `src/services/chat/tests/test_*.py` + `PipelineDiagram.test.tsx`

## Decomposition (TDD tasks)
1. **Deletion sweep + formula-recovery rewire** — remove `orchestrator_workers.py`, `ow_*.py`, `organize` path, `_resolve_workflow`, `tutorWorkflow` knob, harness env flags; `_draft_coro` → one branch; **re-attach formula recovery (`formula_gaps`/`formula_recovery`/`formula_cache`) to the single narrative draft call so `<recovered_equations>` still reaches the synth verbatim**; prune dead tests.
2. **Seam module** (`agents/seams.py`, pure code) — sentence extraction, lemma overlap, boilerplate dedupe, English stopword-ratio, conditional formalize re-link. Unit-tested in isolation first.
3. **Prompt + field-description rewrite** — narrative `DEEP_TUTOR_INSTRUCTIONS`, per-beat bridge `Field` descriptions, `<thesis>` injection, strip `SYNTHESIS_PLAN_PROMPT` tasks.
4. **Wiring** — post-draft seam validation → one silent non-streamed redraft → `quality` scores; **verify final-payload overwrite behavior live.**
5. **Non-interference tests** — seam sentences never contain `$$`; component-eq validator green on narrative output; citation reconcile + figure placement green on new prose shape.
6. **Lockstep surfaces** — `tutorPipeline.ts` + `PipelineDiagram.tsx` (delete OW cluster), `36-deep-tutor.md` mermaid + env table, new `57-tutor-narrative.md`, `Elements/modes/tutor.html`, invariants + changelog.
7. **Live verify on :5175** — bias-variance query (known conv) + no-theorem query (formalize-drop path); modal visual vs `Elements/modes/tutor.html`; final result inspected via Google MCP acting as the user; `rag-verify`.

## Verification gates
Per-task: implementer self-review → spec review → quality review. Whole-impl: opus final review over branch diff. Live human-path (:5175 + Google MCP as user). `rag-verify` invariants (report pre-existing, don't fix). `finishing-a-development-branch`.
