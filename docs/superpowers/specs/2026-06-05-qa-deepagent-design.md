# Q&A Deepagent — Scoped Agentic Retrieval (Design)

**Date:** 2026-06-05 · **Revised:** 2026-06-08
**Status:** Design — revised per user direction (agent roster, thesis/body/conclusion, checker re-call loop)
**Supersedes:** the lean 4-node Q&A graph (`scope → retrieve → generate → verify`) in [`docs/services/chat-features/51-qa-mode.md`](../../services/chat-features/51-qa-mode.md)
**Driving goal:** better grounding/quality via agentic, bounded, decomposition-driven retrieval — answers exactly one question as a **thesis → deep-dive → concise-conclusion** progression, with a checker that re-calls the loop when coverage is insufficient.

---

## 0. Revision 2026-06-08 — what changed vs the original design

| # | Original (2026-06-05) | Revised (2026-06-08) | Why |
|---|---|---|---|
| 1 | `QAAnswer.text` — one lean blob, no structure | `QAAnswer{thesis, body, conclusion}` — 3 fixed fields | User wants an explicit progression of ideas: core answer first, augmented detail, concise conclusion. |
| 2 | Adaptive gate (simple / compound) | **kept** | Confirmed — fast path for simple doubts, fan-out only on real facets. |
| 3 | `verify` advisory only (sets badge) | **Checker** absorbs verify + drives an **env-capped re-call loop** (`QA_MAX_RECHECK=2`) | User wants "another agent checks the result and calls it once more if needed". |
| 4 | Single `grounded-qa` skill | **Three skills** + **per-agent `AGENTS.md`** roster | User wants each subagent to carry AGENTS.md + tools + skills; incorporates patterns from [scientific-agent-skills](https://github.com/k-dense-ai/scientific-agent-skills) (Open Agent Skills `SKILL.md` standard, peer-review/critique loop) and [deep-research-skills](https://skillsllm.com/skill/deep-research-skills) (`Decompose → Search → Synthesize → Verify`, outline-first thesis/body, parallel per-item agents). |

The **anti-tutor-drift guarantee** is restated: the answer is exactly **3 fixed fields** (thesis/body/conclusion) — never the tutor's open-ended `sections`/`aspects`/`figures`. Q&A stays structurally incapable of becoming a tutor.

---

## 1. Motivation

Today's Q&A retrieves **once** on the scoped `target_gap`, then generates. A missed retrieval produces a nakedly wrong/vague punctual answer with no scaffolding to hedge behind. The fix is **agentic retrieval**: retrieval becomes a tool the agent calls, bounded to a few rounds, with pertinence self-checks against the central question; compound questions decompose into per-facet subagents whose findings are fused. A separate **checker** judges whether the fused answer actually covers the gap and, if not, re-runs the loop (bounded).

**Non-goal:** turning Q&A into a second tutor. Decomposition is an internal *retrieval* strategy; thesis/body/conclusion is a fixed *rhetorical* shape, not an open tutor structure.

---

## 2. Architecture

```
scope (deterministic, nano)
  → QAScope{ target_gap, assumed_known, answer_form, complexity, sub_questions[] }
  │
  ├─ simple   → ORCHESTRATOR deepagent: bounded search_corpus loop (≤ QA_MAX_ROUNDS)
  │             evidence offloaded → StoreBackend /sources/
  │
  └─ compound → ORCHESTRATOR deepagent + one ANALYST subagent per sub_question
  │             (isolated context, own search_corpus, /skills/grounded-qa)
  │             → each returns QAFinding{ sub_question, text, citations, pertinent }
  │
  → ORGANIZE (orchestrator, /skills/synthesize-progression):
  │     merge/drop repeated info → QAAnswer{ thesis, body, conclusion, citations, math_blocks }
  │
  → CHECKER (deterministic, nano, /skills/critique-coverage) → QACheck{ sufficient, gaps[], grounding }
  │     sufficient                    → finalize, set grounding badge
  │     gaps & round < QA_MAX_RECHECK → feed gaps back into the orchestrator, RE-RUN  ┐
  │     cap hit                       → finalize, low-confidence badge                │
  └──────────────────────────────────────────── re-call loop ◄───────────────────────┘
```

Two deterministic guardrails wrap the deepagent: a **scope** pre-pass and a **checker** post-loop. The orchestrator owns retrieval + organization in between. This maps directly onto the deep-research `Decompose → Search → Synthesize → Verify` cycle.

### 2.1 Isolation from tutor mode (hard constraint — unchanged)

Rebuilding Q&A must not change a single tutor file, and Q&A must not import tutor logic/prompts/skills.

| Aspect | Rule |
|---|---|
| `ow_deepagents.py`, `orchestrator_workers.py`, `deep_tutor.py` | **Pattern reference only** — never imported. Q&A copies the `create_deep_agent`/`StoreBackend`/`ToolStrategy` idiom into its own module. |
| `prompts/deep_tutor.py`, `DEEP_TUTOR_INSTRUCTIONS` | **Never imported.** Q&A prompts written fresh. |
| `agents/ow_skills/synthesis/` | **Not shared.** Q&A gets its own `agents/qa_skills/`. |
| Frontend `PipelineDiagram.tsx`, `tutorPipeline.ts`, tutor modal | **Untouched.** Q&A keeps `QAPipelineDiagram.tsx` + `qaPipeline.ts` + `QAModeModal`. |

Only shared read-only primitives: `TutorCitation` schema type; `renderInlineWithCites` + `MathBlock` render helpers.

### 2.2 Why an adaptive gate

Always-on decomposition would converge Q&A onto the tutor's `orchestrator_workers`, erasing the fast/punctual niche. The complexity gate (decided in scope) keeps simple doubts on a fast single-loop path; the heavier decompose→subagent→organize path is reserved for genuinely multi-facet questions.

---

## 3. Agent & skill roster

Q&A is a small fleet. Each **agent** has: an *element* (its node id), a *description*, an `AGENTS.md` (persistent operating contract, deepagents virtual-FS file), its *tools*, its *skills*, a `<task>`-scaffolded *system prompt*, and a *response schema*. Deterministic agents (scope, checker) are plain nano calls but still carry an `AGENTS.md` + skill for documentation/consistency.

### 3.1 Skills (`src/services/chat/agents/qa_skills/<name>/SKILL.md`)

Open Agent Skills format — frontmatter `name` + `description` + `metadata.version`, then `## When to use` / `## Instructions` / `## Output`.

| Skill | Owned by | Purpose |
|---|---|---|
| **grounded-qa** | orchestrator, analyst | Bounded agentic retrieval; pertinence to the CENTRAL question; cite every claim with `[n]`; no tutor scaffolding; honesty on corpus-miss. |
| **synthesize-progression** | orchestrator (organize phase) | Fuse findings/evidence into `thesis → body → conclusion`; **merge or drop repeated information**; thesis = answer-first (1–2 sentences); body = augmented connected detail; conclusion = concise wrap. (Adapted from deep-research outline-first synthesis.) |
| **critique-coverage** | checker | Judge sufficiency of the answer vs `target_gap` **and** grounding vs `/sources/`; emit `gaps[]` that trigger a re-call. (Adapted from peer-review / scientific-critical-thinking critique loop.) |

### 3.2 AGENTS.md per agent (`src/services/chat/agents/qa_agents/<name>/AGENTS.md`)

Each is a short operating contract loaded into the agent's virtual FS (orchestrator/analyst) or referenced by the deterministic prompt (scope/checker). Covers: mission, hard rules, which skills to invoke, escalation/stop conditions.

### 3.3 The roster

#### Agent A — **Scope** (deterministic, nano)
- **element:** `scope`
- **description:** Parse the raw question into `QAScope`; classify `simple`/`compound`; emit `sub_questions` for compound; fuzzy-resolve the named book.
- **AGENTS.md:** `qa_agents/scope/AGENTS.md` — "Extract, do not answer. Prefer `simple`. `assumed_known` only from explicit signals."
- **tools:** none (pure LLM parse) + deterministic `resolve_book`.
- **skills:** none (single-shot).
- **system prompt** (`QA_SCOPE_PROMPT`, `<role>/<task>/<output_format>/<rules>`):
  ```
  <role>You parse a student's question into its precise scope.</role>
  <task>Input is the student's question. Classify complexity and, when compound,
  emit focused self-contained sub-questions. Do NOT answer.</task>
  <output_format>JSON: target_gap, assumed_known[], answer_form,
  complexity("simple"|"compound"), sub_questions[] (2–4, compound only).</output_format>
  <rules>Prefer "simple". assumed_known only from explicit "I know…/except…" signals.
  target_gap is the narrowed question, not the whole topic.</rules>
  ```
- **response schema:** `QAScope`. **Fail-open:** parse error → `simple`, whole query as gap.

#### Agent B — **Orchestrator** (deepagent — main)
- **element:** `orchestrator` (renders as `simple`/`compound`/`organize` nodes).
- **description:** Owns retrieval (simple loop) or delegation (compound) + organization. On a re-call it receives the checker's `gaps[]` and targets them.
- **AGENTS.md:** `qa_agents/orchestrator/AGENTS.md` — mission (answer ONE gap), invoke `grounded-qa` to retrieve then `synthesize-progression` to fuse, delegate sub-questions to analysts via the `task` tool, drop non-pertinent findings, never exceed `QA_MAX_ROUNDS`, on re-call address `gaps[]` first.
- **tools:** `search_corpus` (+ `task` delegation tool, auto-provided by deepagents in the compound config).
- **skills:** `grounded-qa`, `synthesize-progression`.
- **system prompt** (`QA_AGENT_PROMPT`, `<role>/<task>/<rules>`):
  ```
  <role>You answer ONE specific question, grounded ONLY in retrieved textbook sources,
  as a thesis → body → conclusion progression.</role>
  <task>Use grounded-qa to gather evidence into /sources/ (≤ the round cap). For a
  compound question, delegate each sub-question to its analyst subagent via the task
  tool. Then use synthesize-progression to FUSE everything into ONE QAAnswer — merge or
  drop repeated information. If given prior gaps, target them first.</task>
  <rules>Answer ONLY target_gap; skip assumed_known. PUNCTUAL — no tutor scaffolding,
  no examples/intuition asides unless answer_form demands it. thesis = direct answer
  (1–2 sentences); body = augmented connected detail with [n] markers; conclusion =
  concise wrap. Cite every claim. Honest one-liner + zero citations on corpus-miss.</rules>
  ```
- **response schema:** `ToolStrategy(QAAnswer)`.

#### Agent C — **Analyst** (deepagent — subagent, compound only, one per sub_question)
- **element:** `analyst-{i}`
- **description:** Research ONE sub-question in isolated context; pertinence-filter against the CENTRAL question; return a grounded `QAFinding`.
- **AGENTS.md:** `qa_agents/analyst/AGENTS.md` — "Your context is isolated; retrieve only for YOUR sub-question but keep only evidence serving the CENTRAL gap; set `pertinent=false` if off-target; never invent sources."
- **tools:** `search_corpus` (own instance, isolated `/sources/`).
- **skills:** `grounded-qa`.
- **system prompt** (`QA_ANALYST_PROMPT`, `<role>/<task>/<rules>`):
  ```
  <role>You research ONE sub-question and report a grounded finding.</role>
  <task>Call search_corpus for your sub-question, read /sources/, return a QAFinding:
  sub_question, terse grounded text with [n] markers, citations, and pertinent =
  whether your evidence serves the CENTRAL question (given in the prompt).</task>
  <rules>Keep only evidence pertinent to the CENTRAL question; set pertinent=false if
  off-target. Ground every claim; never invent sources.</rules>
  ```
- **response schema:** `QAFinding`.

#### Agent D — **Checker** (deterministic, nano)
- **element:** `checker`
- **description:** Judge sufficiency of the drafted answer vs `target_gap` + grounding vs `/sources/`; decide finalize vs re-call.
- **AGENTS.md:** `qa_agents/checker/AGENTS.md` — "You are the critic. Be specific: name concrete gaps. Re-call only for genuine coverage holes, not stylistic nits. Never add facts."
- **tools:** none.
- **skills:** `critique-coverage` (referenced by prompt).
- **system prompt** (`QA_CHECK_PROMPT`, `<role>/<task>/<output_format>/<rules>`):
  ```
  <role>You audit a drafted answer for coverage of the question and grounding in sources.</role>
  <task>Given target_gap, the draft {thesis, body, conclusion}, and numbered sources,
  decide if the gap is fully and correctly answered, and whether every claim is supported.</task>
  <output_format>JSON: sufficient(bool), gaps[] (specific missing/under-covered points,
  empty when sufficient), grounding{ok, unsupported[], confidence 0..1}.</output_format>
  <rules>Re-call only for genuine coverage holes. Do not add facts. Do not rewrite the draft.</rules>
  ```
- **response schema:** `QACheck`. Drives the re-call loop in `run_qa`.

---

## 4. Components

- **`search_corpus(query, k=QA_TOP_K)`** — wraps `hybrid_search(... rerank=True, rerank_top_n=k, adjacent_sections=False)`; writes hits to `/sources/<n>.md` (dedup by `chunkId`); returns a compact numbered brief. `book_slugs` bound at construction.
- **StoreBackend `/sources/`** — virtual FS; orchestrator + each analyst offload evidence; organize phase reads accumulated evidence rather than re-stuffing context.
- **Re-call loop** — outer deterministic loop in `run_qa`: orchestrator → checker; on `not sufficient and round < QA_MAX_RECHECK`, re-invoke orchestrator with `gaps[]` appended to the user message; cap → finalize with the last draft + low-confidence badge.
- **merge/drop repeats** — `synthesize-progression` skill responsibility: overlapping findings deduped; conflicting evidence surfaced, not silently dropped.

---

## 5. Schemas (`src/services/chat/schemas/output.py`)

```python
class QAScope(BaseModel):                       # EXTENDED
    target_gap: str
    assumed_known: list[str] = Field(default_factory=list)
    answer_form: Literal["explanation","definition","comparison",
                         "derivation","yes_no","list"] = "explanation"
    complexity: Literal["simple","compound"] = "simple"     # NEW
    sub_questions: list[str] = Field(default_factory=list)   # NEW (compound only)

class QAFinding(BaseModel):                     # NEW — analyst subagent output
    sub_question: str
    text: str = ""
    citations: list[TutorCitation] = Field(default_factory=list)
    pertinent: bool = True

class QAAnswer(BaseModel):                      # RESHAPED — fixed 3-field progression
    thesis: str                                  # direct core answer (answer-first)
    body: str                                    # augmented deep-dive, merged/deduped, [n] markers
    conclusion: str                              # concise wrap-up
    scope: QAScope
    citations: list[TutorCitation] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)
    grounding: dict = Field(default_factory=dict)   # set by checker

class QACheck(BaseModel):                       # NEW — checker output, drives the loop
    sufficient: bool
    gaps: list[str] = Field(default_factory=list)
    grounding: dict = Field(default_factory=dict)   # {ok, unsupported[], confidence}
```

`QAAnswer.text` is **removed**. Anti-tutor-drift invariant: `QAAnswer` has exactly `{thesis, body, conclusion}` content fields and **no** `sections`/`aspects`/`figures`. Re-export `QAFinding` + `QACheck` from `schemas/__init__.py`. Corpus-miss → `thesis`=honest sentence, `body`/`conclusion`=`""`.

---

## 6. SSE contract

Terminal contract unchanged so the frontend needs no special-casing:

```
meta → [progress…] → structured_output{schema:"QAAnswer"} → sources_full → retrieval_meta → usage → done
```

Progress events (advisory, bridged from stage callbacks):
```
progress{stage:"retrieving", round:n}                  # simple
progress{stage:"analyzing", subQuestions:[…]}          # compound
progress{stage:"rechecking", round:n}                  # checker re-call
```

Corpus-miss path: `structured_output{QAAnswer thesis=honest, citations:[]}` → `sources_full{[]}` → `done`.

---

## 7. Models & cost

nano default for all LLM stages: scope, orchestrator, each analyst, organize (same agent), checker. `stageModels` overrides per stage (keys: `scope`, `agent`, `analyst`, `check`). Cost envelope (nano): simple ≈ scope + 1–3 orchestrator turns + checker (× ≤ `QA_MAX_RECHECK`); compound ≈ scope + N analysts + organize + checker (× re-calls). Gate + caps bound worst case to well under a cent.

---

## 8. Env flags

| Flag | Default | Meaning |
|---|---|---|
| `QA_TOP_K` | `4` | Hits per `search_corpus` call |
| `QA_MAX_ROUNDS` | `3` | Max `search_corpus` rounds (simple path / per analyst) |
| `QA_MAX_RECHECK` | `2` | Max checker-driven re-call rounds |
| `QA_DECOMPOSE` | `1` | Enable compound path (0 = always simple loop) |
| `QA_SCOPE` | `1` | Enable scope pre-pass |
| `QA_CHECK` | `1` | Enable checker (0 = single pass, advisory badge only) |
| `QA_SCOPE_MODEL` / `QA_AGENT_MODEL` / `QA_ANALYST_MODEL` / `QA_CHECK_MODEL` | nano | Per-stage model overrides |

`stageModels` overrides env per call. `"qa"` stays in `settings.use_v2_modes`.

---

## 9. Error handling

- **Scope parse fail** → fail-open simple, whole query as gap.
- **Orchestrator/analyst exception** → fall back to a single deterministic `hybrid_search` + nano generate into a `QAAnswer{thesis,body,conclusion}` so the stream always yields an answer; log.
- **Checker exception** → treat as `sufficient=True`, low-confidence badge (advisory fail-open); no infinite loop.
- **0 retrieved sources** → honest "not covered in selected books", no fabricated citation.
- **`deepagents` import error** → same deterministic fallback.
- SSE stream always terminates in `done`.

---

## 10. Frontend (lockstep)

| Component | Change |
|---|---|
| `web/src/types.ts` | `QAScope` += `complexity`,`sub_questions`; new `QAFinding`,`QACheck`; `QAAnswer` → `thesis`/`body`/`conclusion` (drop `text`) |
| `QAAnswerCard.tsx` | render the progression: thesis (emphasized) → body → conclusion → grounding badge; optional "answered via N sub-questions" hint |
| `qaPipeline.ts` + `QAPipelineDiagram.tsx` | reshape: `scope → gate → {simple loop ‖ analyst subagents} → organize → checker` with the **checker→orchestrator re-call loop edge**; per-LLM-stage model dropdowns |
| `MessageThread.tsx` | handle `progress` (retrieving/analyzing/rechecking); unchanged `schema==="QAAnswer"` branch |
| `ModePicker.tsx` / `QAModeModal.tsx` | unchanged wiring; modal copy updated to the agentic pipeline |

After the diagram change: open the Q&A `(i)` modal on `:5175` and confirm it matches `docs/common ground/Elements/index.html`.

---

## 11. Required-elements checklist (verify EACH at the end)

Per the user's request, every item below must be present and verified (the implementation plan maps each to a task + TodoWrite item):

**Per-agent artifacts** — for each of {scope, orchestrator, analyst, checker}:
- [ ] element id wired into pipeline + diagram
- [ ] description in docs + modal
- [ ] `AGENTS.md` operating contract (`qa_agents/<name>/AGENTS.md`)
- [ ] tools assigned (search_corpus / task / none) and bound correctly
- [ ] skills assigned and loaded into the agent's virtual FS
- [ ] system prompt with `<role>/<task>/<rules>[/<output_format>]` special tokens
- [ ] response schema (`QAScope`/`QAAnswer`/`QAFinding`/`QACheck`)

**Skills** (Open Agent Skills `SKILL.md`):
- [ ] `grounded-qa` · [ ] `synthesize-progression` · [ ] `critique-coverage`

**Behavioural requirements:**
- [ ] thesis → body → conclusion output (3 fixed fields, no tutor fields)
- [ ] adaptive simple/compound gate
- [ ] checker re-call loop, env-capped (`QA_MAX_RECHECK`)
- [ ] merge/drop repeated information in organize
- [ ] per-claim `[n]` citations + grounding badge
- [ ] deterministic fallback (never regress below current behaviour)
- [ ] hard tutor-isolation (grep returns nothing)

**External-skill incorporation (provenance):**
- [ ] Open Agent Skills SKILL.md format ← scientific-agent-skills
- [ ] Decompose→Search→Synthesize→Verify + outline-first thesis/body ← deep-research-skills
- [ ] critique/peer-review loop → checker ← scientific-agent-skills

---

## 12. Lockstep artifacts checklist

| Aspect | Path |
|---|---|
| Agent logic (rebuilt) | `src/services/chat/agents/qa.py` |
| Prompts (`<task>`-scaffolded) | `src/services/chat/prompts/qa.py` (scope/agent/analyst/check) |
| Skills (3) | `src/services/chat/agents/qa_skills/{grounded-qa,synthesize-progression,critique-coverage}/SKILL.md` |
| AGENTS.md (4) | `src/services/chat/agents/qa_agents/{scope,orchestrator,analyst,checker}/AGENTS.md` |
| Schemas | `src/services/chat/schemas/output.py` (+ `__init__` re-export) |
| Mode id / registration | `src/services/chat/schemas/_core.py`, `src/services/chat/modes.py` (no change — regression test only) |
| Dispatch | `src/services/chat/router.py` (no change — regression test only) |
| Cost | `src/services/chat/cost.py` |
| Frontend | `web/src/types.ts`, `QAAnswerCard.tsx`, `qaPipeline.ts`, `QAPipelineDiagram.tsx`, `MessageThread.tsx` |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| Service + feature docs | `docs/services/chat.md`, `docs/services/chat-features/51-qa-mode.md` (rewrite) |
| Tests | per the plan's §11 |

---

## 13. Open questions / future

- **Cross-thread memory** (persist `assumed_known` + prior answers) — deferred; clean future add via `MemoryMiddleware` + `Store`.
- **Pertinence as a dedicated tool** — if skill-driven pertinence proves loose live, promote to a cheap relevance call. Start without it (YAGNI).
- **Parallel analyst execution** — the plan must confirm whether `task` delegation runs analysts concurrently or sequentially; if sequential and latency matters, run analysts via `asyncio.gather` outside the agent loop.
