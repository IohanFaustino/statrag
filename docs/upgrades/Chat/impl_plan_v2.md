# Implementation Plan v2 — Chat Service Upgrade

> Target architecture: [`target_architecture.md`](target_architecture.md).
> Diagnostic source: [`diagnostic.md`](diagnostic.md), `.audit_code_chat.md`, `.audit_synopsis_chat.md`.
>
> **User decisions** (2026-05-18):
> - Vector store stays Qdrant (no change). Chat history + checkpointer → separate SQLite (`data/checkpoints.db`).
> - Frontend untouched during Phase 1 — `router.py` adapter translates LangGraph SSE → v1 schema.
> - Per-mode feature flag: `USE_V2_MODES=tutor,quiz,…` (comma list).
> - LangSmith auto-trace mandatory in dev; opt-out via `LANGSMITH_DISABLED=1`.
> - Strict phase ordering P1 → P2 → P3 → P4.
> - Per-feature cadence: design → test plan → impl → unit + perf test → review → merge.

---

## Ticket structure

Every ticket follows the same shape:

```
ID         Tnn — short title
Goal       single sentence
Closes     bug ID(s) + upgrade ID(s) from diagnostic
Files      paths touched
Approach   brief design notes
Tests
  unit       pytest test file paths + key cases
  perf       pytest-benchmark target + budget
  golden     LLM-on snapshot diff (mode-level)
Acceptance criteria
Rollback   how to revert in <5 min
Effort     S = ≤1 day, M = 2-3 days, L = 1 week
```

---

## Phase 1 — Stop the Bleeding

Goal: every P0 bug fixed. New code lands on LangChain 1.0 + LangGraph; v1 orchestrator deletable at end of phase.

### T01 — Install LangChain 1.0 + scaffold v2 layout · M

**Goal**: dependencies + folder structure ready; no behavior change.

**Closes**: prerequisite for T02-T12.

**Files**:
- `requirements.txt` — bump `langchain==0.3.7` → `langchain>=1.0,<2.0`; add `langgraph>=1.0`, `langsmith>=0.3.0`, `langchain-qdrant`, `langchain-openai`.
- `src/services/chat/mode_impls/` — new dir (empty `.gitkeep`).
- `src/services/chat/retrievers/` — new dir.
- `src/services/chat/tools/` — keep; will populate in T08.
- `src/services/chat/prompts/<mode>/` — restructure per-mode folders.
- `src/core/config.py` — add `use_v2_modes: list[str] = []`, `langsmith_disabled: bool = False`, `checkpointer_db: str = "data/checkpoints.db"`.
- `src/services/chat/router.py` — new file; adapter scaffold (returns v1 path until modes opt in).

**Approach**:
- Install both langchain 1.0 alongside existing langchain 0.3 — verify no import conflicts (ingestion side uses 0.3 patterns).
- Decision: bump ingestion to 1.0 same time, OR pin ingestion to old name (`langchain-classic`)? **Audit ingestion imports for breaking changes.**

**Tests**:
- unit: `tests/test_imports.py` asserts `import langchain`, `import langgraph`, `import langsmith` succeed; `langchain.__version__` ≥ "1.0".
- perf: n/a.
- golden: no behavior change.

**Acceptance**:
- `.venv/bin/python -c "from langchain.agents import create_agent; from langgraph.graph import StateGraph"` exits 0.
- Existing test suite passes (212 backend tests green).
- Ingestion pipeline (`python -m src.ingestion.pipeline --status`) still works.

**Rollback**: `git revert` + `pip install -r requirements.txt.old`.

---

### T02 — SqliteSaver checkpointer + persistence fix · M

**Goal**: replace `memory.py` + missing-SQLite-writes with LangGraph checkpointer. Persistence works end-to-end across turns.

**Closes**: B1, B10.

**Files**:
- `src/services/chat/router.py` — instantiate `SqliteSaver.from_conn_string(settings.checkpointer_db)` once; pass to all v2 agents/graphs.
- `src/services/chat/memory.py` — mark deprecated; keep code for v1 fallback during transition.
- `src/services/chat/api.py` — chat route: ensure `thread_id=conversationId` passed in invoke config. Remove dead `_history` reads when mode is v2.
- `src/services/chat/store.py` — keep `conversations` + `study_plans` + `user_profile` tables; drop `messages` writes for v2 modes (checkpointer owns them).
- `ops/scripts/migrate_messages_to_checkpointer.py` — one-shot migration script for existing conversations.

**Approach**:
- Create `data/checkpoints.db` on first run via `SqliteSaver.setup()`.
- Checkpointer is the ONLY message store for v2 modes.
- Migration script reads `store.get_messages(conv_id)` and seeds checkpointer state per thread.

**Tests**:
- unit: `tests/services/chat/test_checkpointer.py`
  - new thread → state initialised; second invoke sees first turn.
  - two thread_ids isolated.
  - graph state survives process restart (open/close `SqliteSaver`).
- perf: `tests/perf/test_checkpointer.py`
  - 100 sequential turns on one thread; assert P95 write < 50ms, read < 50ms.
- golden: `tests/golden/test_tutor_memory.py`
  - 3-turn conversation: tutor answers turn 3 referencing turn 1 fact. Snapshot stable.

**Acceptance**:
- Existing conversation IDs from `data/chat.db` migrate cleanly via script.
- `curl /api/chat` with same `conversationId` twice → second response sees first as history.
- `len(store.get_messages(conv_id))` for v2 modes stays 0; checkpointer has the data.

**Rollback**: revert flag `USE_V2_MODES`; v1 orchestrator runs against old `memory.py`. Migration script reversible (idempotent).

---

### T03 — Real LLM rewriter + fix expansion fence-strip · S

**Goal**: replace concat-hack `rewriter.py` with proper LLM rewrite (acronym expansion + pronoun resolution + topic-drift guard). Fix `str.strip("```json")` char-set bug.

**Closes**: B2, B6.

**Files**:
- `src/services/chat/rewriter.py` — replace `rewrite_query` with async LLM call to nano model. Prompt: "rewrite as standalone question, resolve pronouns + acronyms from prior turns".
- `src/services/chat/query_expansion.py` — fix `raw.strip("```json")` → `_strip_fences(raw)` helper using regex `^```(?:json)?\s*\n(.*?)\n```$` (DOTALL).
- `src/services/chat/_fences.py` — new helper file; one function reused everywhere.
- `src/services/chat/agents/nodes.py`, `agents/research.py`, `agents/study_path.py` — replace ad-hoc strip with helper.

**Approach**:
- Rewriter caches by `hash(history_tail, message)` → SQLite cache (Phase 2 deeper; v1 use lru_cache for now).
- Skip rewrite when history empty (current message IS the query).

**Tests**:
- unit: `tests/services/chat/test_rewriter.py`
  - first turn: rewrite is no-op (no history).
  - "and the second one?" with prior "what's a heteroscedastic model?" → rewritten as "what's the second type of heteroscedastic model?" (golden snapshot, deterministic LLM).
  - pronoun resolution: "explain it" + prior "OLS" → "explain OLS".
- unit: `tests/services/chat/test_fences.py`
  - ` ```json\n{...}\n``` ` → `{...}`.
  - ` ```{...}``` ` → `{...}`.
  - bare JSON → unchanged.
  - missing trailing fence → still extracts JSON.
- perf: rewriter P95 < 800ms (nano call); fence-strip < 100µs.
- golden: `tests/golden/test_compare_followup.py` — 2-turn compare conversation; second turn uses pronoun. Snapshot.

**Acceptance**:
- `rewrite_query("explain it", history=[user="what is OLS"]) ≠ "what is OLS | explain it"`.
- All existing tests that consumed concatenated string adjusted.

**Rollback**: env `REWRITER_MODE=concat` falls back to v1 behavior.

---

### T04 — Cross-collection RRF fusion (B5) + wire `adjacent_sections` · M

**Goal**: fix invalid score comparison across collections; implement the dead `adjacent_sections` flag.

**Closes**: B5; wires dead flag from diagnostic.

**Files**:
- `src/services/chat/retrieval.py`:
  - `hybrid_search(...)` — when multiple collections, build a single Qdrant `Prefetch` chain that fuses across collections via RRF rather than per-collection then concat-sort.
  - Add `_expand_adjacent(sources, k_each=1)` step gated by `flags.adjacent_sections`. Uses Qdrant payload filter on `chunk_idx ± 1` within same `(book, chapter)`.
- `src/services/chat/retrievers/qdrant_hybrid.py` — new wrapper exposing existing `hybrid_search` as `BaseRetriever` for LangChain agents (used in T08+).

**Approach**:
- Single-collection unchanged; only multi-collection path changes.
- Qdrant Python client supports `Prefetch` with multiple sources merging via `Fusion.RRF`. Verify against current 1.12.4 API.
- `adjacent_sections=True` adds a second Qdrant fetch keyed by `(book, chapter, chunk_idx IN [n-1, n+1])` for each top-k result; dedup before return.

**Tests**:
- unit: `tests/services/chat/test_retrieval_cross_collection.py`
  - Seed 2 collections with mock points; assert top-K respects relative relevance, not absolute RRF score per collection.
- unit: `tests/services/chat/test_retrieval_adjacent.py`
  - Seed collection w/ known chunk_idx ordering; flag on → neighbors appear in expanded set; flag off → no neighbors.
- perf: `tests/perf/test_retrieval.py`
  - hybrid_search P95 < 350ms (1 collection, top_k=5).
  - cross-collection P95 < 500ms (3 collections, top_k=5 each).
  - adjacent_sections adds < 100ms overhead.
- golden: `tests/golden/test_compare_quality.py` — query spanning 3 books; sources include ≥1 from each book.

**Acceptance**:
- Compare mode now has source chunks from every book in scope.
- Figures/math/quiz get adjacent-section context they were promised.

**Rollback**: env `RETRIEVAL_LEGACY=1` reverts to concat-sort behavior.

---

### T05 — Reranker fix: full chunk + asyncio.to_thread · S

**Goal**: pass `chunk[:2000]` not `excerpt[:200]` to cross-encoder; wrap `predict` in `asyncio.to_thread`.

**Closes**: code §3 gaps (no diagnostic ID — incremental).

**Files**:
- `src/services/chat/rerankers.py` — change `pairs = [(q, h.excerpt or h.chunk[:512])]` → `[(q, (h.chunk or h.excerpt or "")[:2000])]`. Wrap `model.predict` in `await asyncio.to_thread(...)`.
- Add `Source.raw_score: float` field; reranker preserves RRF score before overwriting.

**Tests**:
- unit: `tests/services/chat/test_reranker.py`
  - rerank correctly orders 5 candidates against known query; assert top-1 matches expected.
  - `raw_score` preserved on each `Source`.
- perf: rerank 50 candidates P95 < 250ms (CPU); should match v1 within ±10% (more text but same model).
- golden: tutor with sources requiring fine-grained rerank distinction.

**Acceptance**:
- Logs show rerank using full 2000-char context.
- Event loop not blocked (verified by parallel async invocation test).

**Rollback**: env `RERANKER_EXCERPT_ONLY=1` returns to 200-char input.

---

### T06 — Schema validation via `response_format` (replaces ADR-005) · M

**Goal**: native JSON-schema constrained decoding for OpenAI providers; deprecate `_validate_and_repair`.

**Closes**: B6 (entirely); ADR-008.

**Files**:
- `src/services/chat/llm/openai_client.py` — accept `response_format=PydanticSchema` and pass through to API.
- `src/services/chat/schemas/output.py` — audit for `tuple[int, int]` (Annotation.position → `list[int]` w/ min/max len 2 constraint); confirm no Pydantic custom validators that don't serialize to JSON Schema.
- `src/services/chat/orchestrator.py` — when running v1 mode with v2 LLM client: drop fence-strip + repair, expect well-formed JSON. Keep v1 fallback path for DeepSeek (no native json_schema).

**Approach**:
- v1 modes that opt into `response_format` (env-gated) bypass `_validate_and_repair`.
- v2 modes (T08+) all use `response_format` automatically via `create_agent`.

**Tests**:
- unit: `tests/services/chat/test_schema.py`
  - send unconstrained model output → schema validation passes.
  - simulate constrained decoding (mock OpenAI) → no repair call issued.
- perf:
  - structured-mode (quiz) P50 latency before: X ms; after: assert ≤ X − 200ms (no repair retry burden).
  - tokens consumed per turn: assert ≤ 90% of v1 baseline.
- golden: `tests/golden/test_quiz_schema.py` — 50 invocations; 0 SchemaValidationError emitted.

**Acceptance**:
- `grep -n "_validate_and_repair" src/services/chat/` shows usage only in DeepSeek code path.
- LangSmith trace shows native json_schema in request payload.

**Rollback**: env `SCHEMA_REPAIR_LEGACY=1` re-enables repair fallback.

---

### T07 — Multi-agent: fix qc retry hole (B8) + ConceptEdge schema · S

**Goal**: fix `graph.py:78` retry logic; align ConceptEdge `from_id/to_id` vs LLM `from/to`.

**Closes**: B8; code §10 ConceptEdge mismatch.

**Files**:
- `src/services/chat/agents/graph.py` — after retry, re-evaluate `qc_status`. If retry raises, set status `fail` and break (don't continue). Add explicit unit test for the broken case.
- `src/services/chat/agents/nodes.py:139-140` — parse `from_id`/`to_id` (or alias `from`/`to` for backward compat using `e.get("from_id", e.get("from"))`).
- `src/services/chat/prompts/prereqs.py` — confirm prompt asks for `from_id`/`to_id`.

**Tests**:
- unit: `tests/services/chat/agents/test_graph.py`
  - node fails → retry runs; assert qc_status set correctly post-retry (success → "pass"; failure again → "fail" + break).
  - retry exception path: state.errors[] has both original + retry error.
- unit: `tests/services/chat/agents/test_prereqs.py`
  - LLM emits `from`/`to` (legacy) → graph builds.
  - LLM emits `from_id`/`to_id` → graph builds same DAG.
- perf: prereqs end-to-end P95 < 6s (5 sources, 10 concepts).
- golden: `tests/golden/test_prereqs.py` — known concept → expected DAG topology.

**Acceptance**:
- `pytest tests/services/chat/agents/` green.
- Manual run: `python -m src.services.chat.agents.prereqs` produces non-empty edges.

**Rollback**: revert single commit; agents fall back to current behavior (still buggy).

---

### T08 — Tool surface honesty: real `@tool` functions · L

**Goal**: implement the declared-but-fictional tools as real LangChain `@tool` functions. Delete dead `tools[]` entries or wire them.

**Closes**: B3 (entirely).

**Files** (new):
- `src/services/chat/tools/retrieve.py` — `@tool retrieve(query, k=5, book_filter=None)` wrapping `retrievers/qdrant_hybrid.py`.
- `src/services/chat/tools/retrieve_per_book.py` — `@tool retrieve_per_book(query, books, k_per_book=3)` — fans out N hybrid_search calls (asyncio.gather), returns dict[book → sources].
- `src/services/chat/tools/retrieve_figures.py` — wraps `search_figures`.
- `src/services/chat/tools/inspect_figure.py` — re-exposes existing function as `@tool`.
- `src/services/chat/tools/extract_terms.py` — `@tool extract_terms(text)` → list[str]. Nano LLM call.
- `src/services/chat/tools/kg_neighbors.py` — `@tool kg_neighbors(concept_id, depth=1)` → list[ConceptNode]. Wraps `kg.fetch_concepts_by_label`.
- `src/services/chat/tools/__init__.py` — re-exports.

**Approach**:
- Tools accept JSON-serialisable args; return JSON-serialisable types.
- Tool docstrings are LLM-facing → very specific (per langchain-fundamentals skill: "Use this when you need recent data or facts").
- `inspect_figure` retains existing cost-log call.

**Tests**:
- unit per tool: `tests/services/chat/tools/test_<tool>.py`
  - happy path (mock retriever / kg).
  - invalid args → schema validation error.
  - tool docstring lints (mode-test: assert each docstring has `Args:` and ≥ 30 chars description).
- perf: every tool individual P95 documented.
- golden: tool usage trace via LangSmith for sanity check.

**Acceptance**:
- All 6+ tools importable from `src.services.chat.tools`.
- `@tool` schemas serialize to OpenAI function-calling format (assert via `tool.tool_call_schema`).
- Tests green.

**Rollback**: tools unused if not registered to agents in T09; safe to merge ahead.

---

### T09 — Migrate tutor mode to `create_agent` (first cutover) · M

**Goal**: tutor mode runs entirely on LangChain `create_agent`. Frontend untouched via SSE adapter.

**Closes**: starts ADR-006 migration. Reference implementation for T10.

**Files**:
- `src/services/chat/mode_impls/tutor.py` — new file. `create_agent(model=..., tools=[retrieve], system_prompt=load_prompt("tutor", v=1), response_format=TutorAnswer, checkpointer=..., middleware=[...])`.
- `src/services/chat/router.py` — when `req.mode == "tutor"` and `"tutor" in settings.use_v2_modes`, dispatch to v2 agent and translate stream to v1 SSE events. Else fall back to v1 `stream_chat`.
- `src/services/chat/prompts/tutor/v1.md` — unified prompt format; matches existing TUTOR_INSTRUCTIONS.

**Approach**:
- TutorAnswer is the "sentinel" non-structured mode in v1. For v2: still bypass `response_format` (text is fine for tutor); `create_agent` without `response_format` returns free-form text.
- SSE adapter: `graph.astream(..., stream_mode="messages")` yields `(token, metadata)` tuples → translate to `{"type": "token", "text": token.content}` matching v1 schema. `stream_mode="updates"` final → `sources_full`, `retrieval_meta`.

**Tests**:
- unit: `tests/services/chat/modes/test_tutor_v2.py`
  - mock retriever; assert agent invokes `retrieve` with correct query; produces text response.
  - thread_id reuse persists messages.
  - empty history → fresh state.
- integration: `tests/integration/test_tutor_v2_e2e.py`
  - real Qdrant, real LLM (nano), assert non-empty answer + citations.
- perf: `tests/perf/test_tutor_v2.py`
  - P95 end-to-end ≤ 4s (NFR from arch doc).
  - tokens/turn input ≤ 4k, output ≤ 2k.
- golden: `tests/golden/test_tutor_parity.py` — same query through v1 vs v2; answer quality assertions:
  - both cite same source set (intersection ≥ 80%).
  - faithfulness score (Ragas-style; even without full Ragas yet, a token-overlap baseline) ≥ v1.

**Acceptance**:
- `USE_V2_MODES=tutor curl /api/chat -d '{"mode":"tutor", ...}'` works; SSE stream looks identical to frontend.
- v1 path still works for other modes.
- LangSmith dashboard shows tutor traces (auto).

**Rollback**: drop `tutor` from `USE_V2_MODES`. Zero-downtime.

---

### T10 — Migrate remaining single-agent modes · L

**Goal**: compare, figures, quiz, navigate, annotate, math, roadmap on `create_agent`.

**Closes**: completes single-agent migration.

**Files**: one `src/services/chat/mode_impls/<mode>.py` per mode + corresponding `prompts/<mode>/v1.md`.

**Approach**:
- One mode per commit. Per-mode parity test before next.
- Compare uses `retrieve_per_book` tool — first real test of the new tool.
- Figures/math register `inspect_figure` tool; the LLM decides when to call (no more `_is_vision_mode` string match).
- Each mode has `response_format=<schema>` for structured outputs.

**Tests** (per mode):
- unit: mode-specific assertions on tool selection + response shape.
- perf: per-mode P95 latency budget from arch doc NFR table.
- golden: per-mode parity vs v1 (source overlap, schema compliance).

**Acceptance**:
- `USE_V2_MODES=tutor,compare,figures,quiz,navigate,annotate,math,roadmap` → all 8 modes v2.
- All structured modes emit valid schema; no SchemaValidationError in 100-run smoke.

**Rollback**: per-mode flag removal.

---

### T11 — Migrate multi-agent modes to LangGraph · L

**Goal**: prereqs, research, path on `langgraph.graph.StateGraph`. Use `Send` for parallel claim retrieval (research) and per-sub-goal prereqs (path).

**Closes**: completes ADR-006; fixes serial-retrieval latency in research + path.

**Files**:
- `src/services/chat/agents/prereqs.py` — rewrite as LangGraph StateGraph; same 5 nodes but using `langgraph.graph.StateGraph` + `ToolNode` + retry policies.
- `src/services/chat/agents/research.py` — `Send` fan-out for `classify_claim` workers; reducer on `claim_results` field.
- `src/services/chat/agents/study_path.py` — `Send` fan-out for sub-goal → `run_prereqs_subgraph` (LangGraph subgraph composition).
- `src/services/chat/agents/graph.py` — **DELETE** (replaced by langgraph.graph).
- `src/services/chat/agents/state.py` — keep as TypedDict; add reducers where needed.

**Approach**:
- Use `checkpointer=True` on study_path so replan picks up where it left off (free time-travel for `replanned_from_version`).
- Multi-agent stream via `stream_mode="custom"` → frontend gets `agent_step` events.

**Tests**:
- unit: per-graph snapshot test; verify topology after compile.
- perf:
  - research with 6 claims: P95 < 12s (was sequential 8 LLM calls + 6 retrievals; should be ~3-4s w/ Send).
  - path with 5 sub-goals: P95 < 18s (was 35s+ sequential).
- golden: research stance classification on a known 6-claim excerpt.

**Acceptance**:
- All 3 multi-agent modes on LangGraph.
- `agents/graph.py` deleted.
- `pytest tests/services/chat/agents/` green.

**Rollback**: per-mode flag; v1 `agents/graph.py` resurrected from git.

---

### T12 — Delete v1 orchestrator + memory + cost log · S

**Goal**: end Phase 1 by deleting dead code.

**Closes**: cleanup; ADR-001 fully retired.

**Files** (delete or shrink):
- `src/services/chat/orchestrator.py` — DELETE (logic moved to `router.py` + `modes/`).
- `src/services/chat/memory.py` — DELETE (checkpointer replaces).
- `src/services/chat/cost.py` — DELETE (LangSmith replaces — Phase 2 confirmed; if LangSmith deferred, keep until then).
- `src/services/chat/prompts/<mode>/build_prompt` helpers — DELETE (orchestrator no longer calls them).
- `src/services/chat/agents/graph.py` — already deleted in T11.

**Tests**:
- existing test suite still green.
- `grep -rn "from src.services.chat.orchestrator" src/` returns 0 hits.
- `grep -rn "from src.services.chat.memory" src/` returns 0 hits (only the deprecated module if kept for fallback).

**Acceptance**:
- LoC in `src/services/chat/` drops by ≥ 1.5k (orchestrator 565 + memory 350 + cost 100 + dead prompt helpers ≈ 1.1k; plus dead validators, dead build_prompt etc.).
- All v2 modes pass golden tests.
- README + CLAUDE.md updated to reflect v2 architecture.

**Rollback**: revert single deletion commit. (Code recoverable in git.)

---

## Phase 1 — exit criteria

- All 11 modes have `USE_V2_MODES` parity; default `USE_V2_MODES=*` ships.
- Zero `SchemaValidationError` SSE events in 1000-request smoke.
- P95 latencies meet NFR table in arch doc.
- LangSmith traces visible for every chat request.
- v1 dead code removed (T12).
- Diagnostic bugs B1–B10 all closed (verified by per-bug test).

---

## Phase 2 — Faithfulness + UX

Tickets T13–T22 (sketched; expand when Phase 1 ships).

| T# | Title | Closes | Effort |
|----|-------|--------|--------|
| T13 | NLI citation verification post-stream | U1 | M |
| T14 | Chain-of-Verification (CoVe) loop behind `verify_pass` flag | U1 | L |
| T15 | Supervisor QC node for multi-agent | U1, synopsis §8 | M |
| T16 | Query classifier + adaptive RAG router | U6 | M |
| T17 | No-retrieve short-circuit for meta queries | U6 | S |
| T18 | Cascade routing (nano → pro on low confidence) | synopsis §15 | M |
| T19 | `agent_step` SSE events for multi-agent streaming | U7 | S |
| T20 | Partial-JSON streaming for structured modes | U7 | M |
| T21 | LangSmith dashboards + nightly Ragas CI eval | U10 | M |
| T22 | Synthetic test set generator | U10 | M |

## Phase 3 — Longitudinal tutor

Tickets T23–T31 (memory + personalisation).

| T# | Title | Closes | Effort |
|----|-------|--------|--------|
| T23 | Episodic/semantic/procedural memory namespaces in Store | U3 | M |
| T24 | Memory consolidation pass (LLM summary, periodic) | U3 | M |
| T25 | Importance scoring + recency-weighted recall | U3 | S |
| T26 | Cross-conversation user_profile (SQLite Store) | U3 | M |
| T27 | Adaptive difficulty in quiz mode | synopsis §16 | M |
| T28 | Spaced-repetition `review_queue` table | synopsis §16 | M |
| T29 | Hypothetical-question index ingestion + retrieval channel | U2 | L |
| T30 | Parent-document retrieval | U2 | M |
| T31 | `clarify_request` SSE + HITL clarification node | synopsis §2 | M |

## Phase 4 — Agentic + KG + Vision

Tickets T32–T41.

| T# | Title | Closes | Effort |
|----|-------|--------|--------|
| T32 | MCP server export (retrieve, inspect_figure, kg_neighbors) | synopsis §10 | M |
| T33 | Self-RAG wrapper for research mode | synopsis §7 | L |
| T34 | Corrective RAG retrieval evaluator | synopsis §7 | M |
| T35 | Reflexion for path replan | synopsis §7 | M |
| T36 | Debate sub-graph for research mode | synopsis §8 | L |
| T37 | Entity linking on query → KG canonical IDs | synopsis §9 | M |
| T38 | GraphRAG community summaries (Leiden clustering) | synopsis §9 | L |
| T39 | HippoRAG personalized PageRank recall | synopsis §9 | M |
| T40 | CLIP joint embeddings for figures | synopsis §11 | L |
| T41 | Vision-aware rerank | synopsis §11 | M |

---

## Cross-cutting infrastructure (Phase 1.5)

These can land between Phase 1 and Phase 2 if needed:

| T# | Title |
|----|-------|
| T-A | `tests/perf/conftest.py` — pytest-benchmark fixtures, asyncio support, Qdrant test-collection seeding |
| T-B | `tests/golden/` runner — snapshot diff with semantic-similarity tolerance (cosine ≥ 0.9 between v1 vs v2 LLM answers) |
| T-C | `ops/scripts/nightly_eval.py` — runs Ragas synth set + writes baseline to `data/eval/baseline.sqlite` |
| T-D | LangSmith project setup script — creates project, sets envs, validates trace export |
| T-E | Feature-flag adapter middleware — `USE_V2_MODES` parsing + per-request flag injection |

---

## Open questions before T01

1. **Ingestion side LangChain version**: bump together (0.3 → 1.0) or keep ingestion on 0.3 by aliasing `langchain-classic`? Recommend audit before T01 starts.
2. **Postgres for checkpointer in dev**: stay SQLite (simpler) or pre-emptively run Postgres in docker-compose? Current ops/docker only has Qdrant.
3. **Existing test suite**: any tests that mock `memory.py` directly need rewriting in T02; quick survey to estimate effort.
4. **LangSmith account**: free tier ≥ 5k traces/month; bigger?

---

## What I propose next

Confirm:
1. Plan looks good as-is → start with **T01** (deps + scaffold) which is purely additive.
2. Or change something in T01-T12 ordering / scope before kickoff.
3. Or want a deeper design dive into one specific ticket (e.g. T08 tool surface, T11 LangGraph migration) before committing?
