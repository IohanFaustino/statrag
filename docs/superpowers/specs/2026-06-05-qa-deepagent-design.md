# Q&A Deepagent — Scoped Agentic Retrieval (Design)

**Date:** 2026-06-05
**Status:** Design — awaiting user review
**Supersedes:** the lean 4-node Q&A graph (`scope → retrieve → generate → verify`) documented in [`docs/services/chat-features/51-qa-mode.md`](../../services/chat-features/51-qa-mode.md)
**Driving goal:** better grounding/quality via agentic, bounded, decomposition-driven retrieval — while keeping Q&A *punctual* (answers exactly one question, no tutor-style scaffolding).

---

## 1. Motivation

Today's Q&A retrieves **once** on the scoped `target_gap`, then generates. When that single retrieval misses (under-retrieves, or conflates a compound question's facets), the punctual answer is nakedly wrong or vague — Q&A has no scaffolding to hedge behind, so a missed retrieval is a visible failure.

The fix is **agentic retrieval**: retrieval becomes a tool the agent calls, bounded to 2–3 rounds, with a pertinence self-check against the central question. For genuinely compound questions, the question is decomposed into sub-questions, each retrieved in isolation, then the findings are fused into one scoped answer.

**Non-goal:** turning Q&A into a second tutor. Decomposition is an internal *retrieval* strategy, not an *output* structure. The reply stays one scope-delimited response — no recommendations, examples, or intuitions.

---

## 2. Architecture

```
scope (deterministic, nano)
  → QAScope{ target_gap, assumed_known, answer_form,
             complexity: simple|compound, sub_questions[] }
  │
  ├─ simple   → deepagent: bounded loop (≤ QA_MAX_ROUNDS search_corpus calls)
  │             pertinence self-check vs target_gap; hits offloaded to /sources/
  │
  └─ compound → deepagent: one analyst SUBAGENT per sub_question, run in
                parallel, isolated context → each returns QAFinding
                { sub_question, text, citations[], pertinent } → organizer fuses
  │
  → organizer emits QAAnswer via ToolStrategy(QAAnswer)
  → verify (deterministic, nano, advisory) → grounding badge
```

Three stable stages wrap the agent: a deterministic **scope** pre-pass and a deterministic **verify** post-pass are hard quality gates; the **deepagent** owns retrieval + drafting in between. This preserves the two guardrails the current pipeline relies on while moving retrieval from one-shot to agentic.

### 2.1 Isolation from tutor mode (hard constraint)

**Rebuilding Q&A must not change a single tutor file, and Q&A must not import tutor logic/prompts/skills.** Coupling the two means a Q&A change could force a tutor change (or silently break it) — that is forbidden.

| Aspect | Rule |
|---|---|
| `ow_deepagents.py`, `orchestrator_workers.py`, `deep_tutor.py` | **Pattern reference only** — do *not* import from them. Q&A copies the `create_deep_agent`/`StoreBackend`/`ToolStrategy` construction idiom into its own module. |
| `prompts/deep_tutor.py`, `DEEP_TUTOR_INSTRUCTIONS` | **Never imported.** Q&A's agent system prompt and `grounded-qa` skill are written fresh and standalone. |
| `agents/ow_skills/synthesis/` | **Not shared.** Q&A gets its own skill dir `agents/qa_skills/grounded-qa/`. |
| Figure helpers (`_format_figure_bundle`) | **Not used** — Q&A has no figures. |
| Frontend `PipelineDiagram.tsx`, `tutorPipeline.ts` | **Untouched.** Q&A keeps its own `QAPipelineDiagram.tsx` + `qaPipeline.ts`. |
| Tutor modal / `AboutModelModal` | **Untouched.** Q&A keeps `QAModeModal`. |

**Only shared primitives — read-only, stable, generic (not tutor structure):**
- `TutorCitation` schema type — already reused by the current `QAAnswer`; a generic citation record, not tutor logic. Kept as-is (giving Q&A its own copy would be churn for no benefit). Q&A must not modify it.
- Generic render helpers `renderInlineWithCites` + `MathBlock` — already used by `QAAnswerCard`; shared UI primitives, not tutor-specific components. Unchanged.

Net: Q&A owns `qa.py`, `prompts/qa.py`, `qa_skills/grounded-qa/`, its QA schemas, and its frontend card/modal/diagram. The lockstep checklist in §12 touches **zero** tutor files.

### 2.2 Why an adaptive gate

Always-on decomposition + subagents would converge Q&A onto the tutor's existing `orchestrator_workers` pipeline, erasing the fast/punctual niche and duplicating machinery. The **complexity gate** (decided in the scope pre-pass) keeps simple doubts on a fast single-loop path and reserves the heavier decompose→subagent→organize path for questions that actually have multiple facets.

---

## 3. Deepagents features — final selection

Built on `deepagents==0.6.8` (already a prod dependency), following the proven pattern in `src/services/chat/agents/ow_deepagents.py` (tutor L6/L7 structured synth): `create_deep_agent` + `StoreBackend` virtual FS + `skills` + `ToolStrategy` structured output, invoked via `asyncio.to_thread`.

| Feature | Used | Rationale |
|---|---|---|
| **Tools** (`search_corpus`) | ✅ core | Retrieval as a callable tool *is* the iterative-retrieval fix. |
| **Filesystem** (`StoreBackend`, `/sources/`) | ✅ | Each retrieval round / subagent writes hits to `/sources/N.md`; organizer reads accumulated evidence before fusing, instead of re-stuffing context. Context offload. |
| **Subagents** | ✅ compound path only | One analyst per sub-question: isolated context (sub-question A's chunks don't pollute B's); concurrency targeted (counters added latency) — actual parallelism confirmed in the plan (see §4.4). |
| **Skills** (`grounded-qa`) | ✅ | Encodes the grounding discipline + the anti-tutor-drift rules. Keeps system prompt lean; mirrors tutor's synthesis-skill pattern. |
| **Structured output** (`ToolStrategy(QAAnswer)`) | ✅ | Lean schema is the structural guarantee against tutor drift; keeps the SSE/frontend contract unchanged. |
| **Prompt caching** | ✅ | Free latency/cost win on the stable system-prompt + skill prefix. |
| **Planning / TodoList** | ❌ skip | A bounded ≤3-round loop does not need a todo list. (Core middleware stays loaded but unprompted — it cannot be removed.) |
| **Memory** (cross-thread Store) | ❌ skip v1 | Persisting `assumed_known` across turns is the *capability* goal, not the *grounding* goal. Clean future add. |
| **Sandboxes / HITL** | ❌ skip | No code execution, no approvals in a read-only answer path. |

---

## 4. Components

### 4.1 Scope pre-pass — `extract_scope` (deterministic, nano)

Extends today's scope node. One LLM call (`QA_SCOPE_PROMPT`, schema `QAScope`) now also classifies complexity and, when compound, emits the sub-questions.

- `complexity: "simple" | "compound"` — compound when the question has ≥2 distinct facets that each warrant their own retrieval.
- `sub_questions: list[str]` — present only when `complexity == "compound"`; each is a focused, self-contained retrieval query. Empty for simple.
- Fail-open: any parse error → `complexity="simple"`, `sub_questions=[]`, `target_gap=whole query`.

### 4.2 `search_corpus` tool

```
search_corpus(query: str, k: int = QA_TOP_K) -> str
```

Wraps `retrieval.hybrid_search(query, book_slugs=…, top_k=k, rerank=True, rerank_top_n=k, adjacent_sections=False)`. Side effect: writes each hit to `/sources/<n>.md` in the StoreBackend (dedup by `chunkId`). Returns a compact numbered brief (book · chapter · section · title + short preview) for the agent to reason over. `book_slugs` is bound at agent-construction time (resolved before the agent runs), so the tool signature stays `(query, k)`.

### 4.3 Deepagent — simple path

`create_deep_agent(model, tools=[search_corpus], skills=["/skills/"], backend=StoreBackend, store, response_format=ToolStrategy(QAAnswer))`. System prompt: short pointer to the `grounded-qa` skill. The agent retrieves (≤ `QA_MAX_ROUNDS` rounds), self-checks coverage of `target_gap`, re-queries with a refined query if uncovered, then emits `QAAnswer`.

### 4.4 Deepagent — compound path (subagents)

Main agent is configured with one subagent per `sub_question`:

```python
subagents = [{
  "name": f"analyst-{i}",
  "description": f"Retrieve and ground sub-question: {sq}",
  "system_prompt": "<grounded analyst — retrieve, pertinence-filter vs the CENTRAL question, return a QAFinding>",
  "skills": ["/skills/"],          # skills are NOT inherited — passed explicitly
  "response_format": QAFinding,
} for i, sq in enumerate(sub_questions)]
```

Each analyst calls `search_corpus` for its sub-question, keeps only chunks pertinent to the **central** `target_gap` (sets `pertinent`), and returns a `QAFinding`. The main agent (organizer) reads the findings + `/sources/`, drops non-pertinent ones, and fuses into a single lean `QAAnswer`. Subagents are delegated via the deepagents `task` tool; concurrency depends on the harness's delegation semantics — the implementation plan must confirm whether `task` calls run concurrently or sequentially and, if sequential, whether running analysts directly via `asyncio.gather` (outside the agent loop, as `ow_deepagents` does for some paths) better serves the latency goal.

### 4.5 Pertinence filter

Anchored to the **central** `target_gap`, not the sub-questions — a chunk retrieved for a sub-question is kept only if it serves the actual asked gap. Implemented as skill-driven agent reasoning (the analyst sets `QAFinding.pertinent` and the organizer honors it), **not** a separate per-chunk LLM scoring call — YAGNI, keeps cost bounded.

### 4.6 `grounded-qa` skill — `agents/qa_skills/grounded-qa/SKILL.md`

Encodes the discipline:
- Answer **only** `target_gap`. Skip everything in `assumed_known`.
- **No tutor scaffolding** — no recommendations, no worked examples, no "intuition" asides, no multi-section structure — unless `answer_form` explicitly is `list`/`derivation`/etc.
- Re-query rule: if `target_gap` is not covered after a round, refine the query and retry; stop at `QA_MAX_ROUNDS`.
- Pertinence: keep only evidence on the central question.
- Cite every claim with `[n]` markers tied to `/sources/`.
- Honesty: if the corpus does not cover it, say so in one sentence; no fabricated citation.

### 4.7 Verify post-pass — `verify_grounding` (deterministic, nano, advisory)

Unchanged behaviour: audits the draft against `/sources/`, returns `grounding{ok, unsupported[], confidence}`, never suppresses the answer (degrades the badge instead). Fail-open.

---

## 5. Schemas (`src/services/chat/schemas/output.py`)

```python
class QAScope(BaseModel):            # EXTENDED
    target_gap: str
    assumed_known: list[str] = Field(default_factory=list)
    answer_form: Literal["explanation","definition","comparison",
                         "derivation","yes_no","list"] = "explanation"
    complexity: Literal["simple","compound"] = "simple"     # NEW
    sub_questions: list[str] = Field(default_factory=list)    # NEW (compound only)

class QAFinding(BaseModel):          # NEW — subagent output
    sub_question: str
    text: str
    citations: list[TutorCitation] = Field(default_factory=list)
    pertinent: bool = True

class QAAnswer(BaseModel):           # UNCHANGED — lean by design
    text: str
    scope: QAScope
    citations: list[TutorCitation] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)
    grounding: dict = Field(default_factory=dict)
```

`QAAnswer` staying lean (no `sections`/`aspects`/`figures`) is the structural guarantee that Q&A cannot emit a tutor-shaped answer. Re-export the new `QAFinding` from `schemas/__init__.py`.

---

## 6. SSE contract

The terminal contract is unchanged so the frontend needs no special-casing:

```
meta → structured_output{schema:"QAAnswer"} → sources_full → retrieval_meta → usage → done
```

Corpus-miss path unchanged (`structured_output{QAAnswer, citations:[]}` → `sources_full{[]}` → `done`).

**Added progress events** (polish): the agent runs via blocking `invoke` (no token streaming, same as today), so during the 2–3s run emit lightweight status events bridged from tool-call callbacks:

```
progress{stage:"retrieving", round:n}                 # simple path
progress{stage:"analyzing", subQuestion:"…", i, of}   # compound path
```

These are advisory — the UI shows live progress instead of a bare spinner, and degrades gracefully if absent. They appear between `meta` and `structured_output`.

---

## 7. Models & cost

nano (`gpt-5.4-nano-2026-03-17`) default for **all** LLM stages: scope, agent loop, each subagent, verify. `stageModels` request field overrides per stage (keys: `scope`, `agent`, `analyst`, `verify`). Iterative retrieval — not model size — does the grounding work.

Cost envelope (rough, nano):
- **simple:** scope + 1–3 agent turns + verify ≈ 3–5 nano calls.
- **compound:** scope + N analyst subagents (parallel) + organizer + verify ≈ (4 + N) nano calls. With N typically 2–3, still well under a cent per answer.

`QA_MAX_ROUNDS` and the compound-only gate bound worst-case cost.

---

## 8. Env flags

| Flag | Default | Meaning |
|---|---|---|
| `QA_TOP_K` | `4` | Hits per `search_corpus` call |
| `QA_MAX_ROUNDS` | `3` | Max `search_corpus` rounds on the simple path (and per subagent) |
| `QA_DECOMPOSE` | `1` | Enable the compound path (0 = always simple loop, no subagents) |
| `QA_SCOPE` | `1` | Enable scope pre-pass (0 = raw query as gap, simple) |
| `QA_VERIFY` | `1` | Enable verify post-pass |
| `QA_SCOPE_MODEL` / `QA_AGENT_MODEL` / `QA_ANALYST_MODEL` / `QA_VERIFY_MODEL` | nano | Per-stage model overrides |

`stageModels` overrides env per call. `"qa"` stays in `settings.use_v2_modes`.

---

## 9. Error handling

- **Scope parse fail** → fail-open simple, whole query as gap.
- **Agent/subagent exception** → fall back to a single deterministic `hybrid_search` + nano generate (today's path) so the stream always yields a `QAAnswer`; log the exception. This guarantees the deepagent rebuild never regresses below the current behaviour.
- **0 retrieved sources** → honest "not covered in selected books", no fabricated citation (unchanged).
- **Verify fail** → keep draft, low-confidence badge (unchanged).
- **`deepagents` import error** → same deterministic fallback as agent exception (deepagents is a prod dep, so this is defensive only).
- SSE stream always terminates in `done`.

---

## 10. Frontend (lockstep)

| Component | Change |
|---|---|
| `web/src/types.ts` | `QAScope` += `complexity`, `sub_questions`; new `QAFinding`; `QAAnswer` unchanged |
| `QAAnswerCard.tsx` | unchanged render (lean answer + scope line + grounding badge); optionally show "answered via N sub-questions" hint from `scope.complexity` |
| `qaPipeline.ts` + `QAPipelineDiagram.tsx` | reshape modal: `scope → gate → {simple loop ‖ compound subagents} → organize → verify`; per-LLM-stage model dropdowns; `search`/retrieval as fixed data label |
| `MessageThread.tsx` | progress-event handling (show stage/round); unchanged answer branch on `schema==="QAAnswer"` |
| `ModePicker.tsx` | unchanged |

After the diagram change: open the Q&A `(i)` modal on `:5175` and confirm it matches `docs/common ground/Elements/index.html`.

---

## 11. Testing

Python (`src/services/chat/tests/`):
- `test_qa_schema.py` — `QAScope` new fields, `QAFinding`, `QAAnswer` unchanged.
- `test_qa_scope.py` — complexity classification (simple vs compound) + sub_question extraction; fail-open.
- `test_qa_tool.py` — `search_corpus` writes `/sources/`, dedups, returns brief.
- `test_qa_simple.py` — bounded loop ≤ `QA_MAX_ROUNDS`; re-query on miss; corpus-miss honest answer.
- `test_qa_compound.py` — N subagents → N findings; non-pertinent dropped; organizer emits lean `QAAnswer` (asserts no tutor fields).
- `test_qa_fallback.py` — agent exception → deterministic fallback still yields `QAAnswer`.
- `test_qa_run.py` / `test_qa_mode_registry.py` / `test_mode_routing_contract.py` — SSE sequence incl. progress events; registry; exhaustive routing.

Frontend: `qaPipeline.test.ts` (new node/edge shape), `QAPipelineDiagram.test.tsx`, `QAAnswerCard.test.tsx`, `types.qa.test.ts`.

Deepagent invocations are monkeypatched in tests (set `qa.create_deep_agent`), matching the `ow_deepagents` test pattern — no live LLM calls in unit tests.

---

## 12. Lockstep artifacts checklist

| Aspect | Path |
|---|---|
| Agent logic (rebuilt) | `src/services/chat/agents/qa.py` |
| Prompts | `src/services/chat/prompts/qa.py` (scope += complexity/sub-questions; generate → grounded-qa rules) |
| Skill (new) | `src/services/chat/agents/qa_skills/grounded-qa/SKILL.md` |
| Schemas | `src/services/chat/schemas/output.py` (+ `__init__` re-export) |
| Mode id / registration | `src/services/chat/schemas/_core.py`, `src/services/chat/modes.py` |
| Dispatch | `src/services/chat/router.py` |
| Cost | `src/services/chat/cost.py` |
| Frontend types / card / modal / thread | `web/src/types.ts`, `QAAnswerCard.tsx`, `qaPipeline.ts`, `QAPipelineDiagram.tsx`, `MessageThread.tsx` |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| Service doc | `docs/services/chat.md` |
| Feature doc | `docs/services/chat-features/51-qa-mode.md` (rewrite) |
| Tests | per §11 |

---

## 13. Open questions / future

- **Cross-thread memory** (persist `assumed_known` and prior answers across turns) — deferred; the capability-goal extension, clean to add later via `MemoryMiddleware` + `Store`.
- **Pertinence as a tool** — if skill-driven pertinence proves too loose in live testing, promote it to a cheap dedicated relevance call. Start without it (YAGNI).
