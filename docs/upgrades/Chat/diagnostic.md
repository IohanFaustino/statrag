# Chat Service — Diagnostic & Upgrade Map

> Synthesis of two parallel audits:
> - **Code audit** — full read of `src/services/chat/**`. Output: `.audit_code_chat.md` (678 lines).
> - **Synopsis mining** — every literature note in `docs/upgrades/Chat/synopsis/` (43 files). Output: `.audit_synopsis_chat.md` (430 lines).
>
> Each feature below: **current implementation → bugs/gaps → literature-backed upgrades**. Sections end with prioritised proposal.

---

## TL;DR — Executive Summary

### Most consequential bugs (ship-blockers)

| # | Bug | Where | Effect |
|---|-----|-------|--------|
| B1 | Chat history never written to SQLite | `api.py:70-98` (chat route reads but never writes) | Conversations don't persist. Memory `sliding`/`summary` get nothing across turns. Frontend shows only initial state. |
| B2 | `rewriter.py` is a context concatenator, not a rewriter | `rewriter.py:63` `" \| ".join(turns + [query])` | Concatenated string feeds BM25, HyDE, multi-query, decompose, **and** rerank pivot — corrupts every retrieval signal. Promised LLM rewrite is permanent TODO. |
| B3 | Tool surface entirely fictional | `modes.py:200,291,218,328` declare tools | `retrieve_per_book`, `extract_terms` don't exist. `inspect_figure` only reachable via hardcoded vision branch. `max_tool_calls`, `few_shot`, `post_validators` read by nothing. Every "single-agent" mode = one-shot RAG. |
| B4 | `post_validators` are dead strings | every `ModeSpec` | `cycle_check`, `self_check`, `latex_check`, `coverage_check`, `yaml_schema`, `stance_consistency` — none dispatched. Modes lie about what they enforce. |
| B5 | Cross-collection RRF score comparison is invalid | `retrieval.py:204` `all_points.sort(key=lambda p: p.score)` | When user spans multiple fields, top-K biased by whichever collection produced higher absolute fused values, not actual relevance. |
| B6 | Schema-repair fence stripping breaks JSON | `orchestrator.py:151-156` `"\n".join(lines[1:-1])` | When LLM emits ` ```json` without trailing fence, last content line is dropped. Also `str.strip("```json")` is char-set strip, not substring. |
| B7 | Cost log = vision-only ledger | only `tools/inspect_figure.py:70` calls `log_call` | Main LLM stream, rewriter, expansion, memory summarise, all agent nodes — invisible. No per-turn / per-session cost accounting. |
| B8 | Multi-agent "graph" is linear-with-one-retry | `agents/graph.py:51-86` | No conditional edges, no fan-out, no parallel. `qc_status` retry has logic hole (line 78 — never re-set on retry exception). |
| B9 | Compare mode cannot actually compare per-book | declared `retrieve_per_book` doesn't exist; uses plain RRF | One book dominates candidate set; schema demands one `BookSection` per book — LLM has to guess from mixed-book context. |
| B10 | Memory `index_turn` writes Qdrant but SQLite never updated | `orchestrator.py:489-498` + `api.py` | Vec memory grows; chat history doesn't. Memory & conversation decoupled. |

### Top upgrade opportunities (highest literature-backed impact)

| # | Upgrade | Sources | Why now |
|---|---------|---------|---------|
| U1 | **NLI citation verification + Chain-of-Verification (CoVe)** | A06, B05, B08, C10, P10 | Closes "is this grounded?" gap. Trust win for tutor/quiz/research/math. Surfaces per-sentence underline signal. |
| U2 | **Hypothetical-question index + parent-document retrieval + cross-collection fusion** | A06, B04, P07 | Three composable retrieval upgrades attacking cross-book vocabulary mismatch + figure context loss. No DB change. |
| U3 | **Hierarchical memory (episodic/semantic/procedural) + user profile + adaptive difficulty** | B02, C07, C08, C11 | Turns one-shot chat into longitudinal tutor. Differentiator for quiz/path/roadmap. |
| U4 | **Real tool-use (function calling) + retrieval-as-tool** | C05, P08, A09 | Replaces fictional `tools[]` with actual function calling. Unlocks agentic-retrieval, mid-generation re-query, memory tools. |
| U5 | **Native JSON-schema constrained decoding** | C03, P02 | OpenAI `response_format=json_schema` ≈ eliminates ADR-005 repair retries. Lower cost, lower latency, fewer failures. |
| U6 | **Query classifier + adaptive RAG routing** | A06, P07, P08, B08 | No-retrieve short-circuit for meta queries; cascade cheap → expensive on confidence. Cuts cost + latency. |
| U7 | **Streaming multi-agent — surface intermediate steps** | B08, P08 | Multi-agent modes are dead air for users; emit `agent_step` SSE events. UX win, zero arch change. |
| U8 | **Real LLM rewriter w/ acronym + pronoun resolution + topic-drift guard** | A06 query transformation, P07 | Fixes B2 root cause. Enables all downstream retrieval signals. |
| U9 | **Embedding + result caching** | A10, B06 | Repeat queries are free. SQLite-backed, simple. Big cost win on demo loops. |
| U10 | **Eval harness w/ Ragas metrics + synthetic test set + nightly CI** | B05, B06, P10 | No regression safety today. Required before any of U1-U9 ships without breaking other modes. |

---

## Per-feature diagnostic

### 1. Retrieval (hybrid, RRF, BM25, dense)

**Now**: `hybrid_search` — Qdrant per-collection RRF fusing dense (`text-embedding-3-large`) + sparse (`Qdrant/bm25`). Per-field collections. `multi_query_hybrid_search` fan-outs queries in parallel.

**Gaps** (`B5`, code §1):
- Cross-collection score comparison invalid (B5).
- Fresh OpenAI client per call → TLS handshake overhead.
- Rerank pivot uses concatenated rewriter string (B2 amplifier).
- `async_hybrid_search` defined but unused — orchestrator calls sync `hybrid_search` from coroutine (event-loop blocker).
- `adjacent_sections` flag is decorative — `retrieval.py` doesn't read it.

**Literature upgrades** (synopsis §1, §5, §11):
- **ColBERT / late-interaction multi-vector** retrieval as opt-in fallback on low-confidence RRF (A06, B03, P07).
- **Metadata-conditioned pre-filter** — push book/chapter/page into Qdrant `filter=` rather than post-rerank (P04, P07). Direct enabler for `compare`/`navigate`.
- **Adjacent-chunk context enrichment** — implement the dead `adjacent_sections` flag: fetch `chunk_idx ± 1` post-retrieval (A06). Fixes figures/math context-loss.
- **Parent-document retrieval** — index small propositions, expand to parent on retrieve (B04, P07).
- **Hypothetical-question index** — `<field>_qa` collection, RRF-merge as 3rd channel (A06, P07).
- **Cross-collection RRF fusion** done properly via Qdrant compound `Prefetch` across collections, not concat-and-sort (B04).

**Proposal — track R**: P0 fix B5; P0 implement `adjacent_sections`; P1 cross-collection RRF; P2 hypothetical-question index.

---

### 2. Query expansion (rewrite, HyDE, multi_query, decompose)

**Now**: `query_expansion.py` — async `hyde`, `multi_query`, `decompose`. `rewriter.py` is heuristic concat (no LLM).

**Gaps** (`B2`, `B6`, code §2):
- Rewriter is not a rewriter (B2).
- HyDE passage feeds BM25 sparse too — opposite of HyDE design intent.
- `str.strip("```json")` char-set strip bug.
- No timeouts.
- Expansions run sequential `await`, not `asyncio.gather`.
- Dedup uses `.lower().strip()` → punctuation-only differences merged.

**Literature upgrades** (synopsis §2, §15):
- **Real LLM rewriter** with acronym expansion + pronoun resolution + topic-drift mitigation (U8).
- **Step-back prompting** — abstract Q first, retrieve, narrow (A06, P07). Fit: prereqs, research.
- **Chain-of-Verification (CoVe)** — re-retrieve via verification Qs after initial answer (C10, B08, P08). Fit: research, math, tutor.
- **Query classifier** upstream — route simple vs complex to different expansion strategies (A06, P07).
- **Clarification node** — when intent ambiguous, emit `clarify_request` SSE and pause (B08, C11). Fit: navigate, path, roadmap.

**Proposal — track Q**: P0 fix B2 (real LLM rewriter); P0 fix B6 substring strip; P1 query classifier + adaptive routing; P2 CoVe loop.

---

### 3. Reranker (cross-encoder)

**Now**: `BAAI/bge-reranker-v2-m3` via `sentence-transformers`. Process singleton. Gated on `ModeSpec.retrieval_flags.rerank`.

**Gaps** (code §3):
- Reranker sees only `excerpt` (200 chars) — wastes the 512-token capacity.
- `CrossEncoder.predict` runs sync on event-loop thread — no `to_thread` wrapper.
- `Source.score` overwritten by rerank logit — RRF rank lost.

**Literature upgrades** (synopsis §3):
- **Listwise LLM reranker (RankGPT)** behind a flag, nano model on top-20 (A06, P07). Fit: research, compare.
- **Multi-stage cascading rerank** — fast bge → slow listwise on top-10 (B04).
- **Diversity-aware / MMR rerank** — `mmr_lambda` parameter penalising redundancy (B04, P07). Direct win for compare (force one chunk per book) and research (diverse stances).
- **monoT5 local fallback** — small ranker selectable via config (A06, P07).

**Proposal — track K**: P0 pass `chunk[:2000]` not `excerpt` to reranker; P0 wrap in `to_thread`; P1 MMR; P2 listwise LLM.

---

### 4. Memory (sliding, summary, vec, auto, persist, off)

**Now**: 5 strategies in `memory.py`. `_resolve_strategy` auto-tiers by turn count. Per-conversation `conv_<id>` Qdrant collection. `index_turn` writes after stream.

**Gaps** (`B10`, code §5):
- SQLite chat history never written by `api.py` (B10) → `sliding`/`summary` strategies read empty history.
- Embedding input `content[:8000]` is char-based, not token-aware — silent truncation against `text-embedding-3-large` 8192-token cap.
- Fresh `AsyncOpenAI` client per call.
- `persist` strategy = identical to `vec` at retrieval; DELETE route always nukes collection (docstring lies).
- Dedup uses `(role, content[:200])` — fragile prefix slice.
- Existence check on Qdrant collection scans all collections per recall (`_vec_retrieve`).

**Literature upgrades** (synopsis §6, §16, §19):
- **MemGPT-style virtual memory** — `recall(query)` + `commit(fact)` as LLM-callable tools (B02, C08).
- **Episodic / semantic / procedural split** — three namespaces in `conv_<id>` (B02, C08). Episodic = turns; semantic = learner facts; procedural = strategy success log.
- **Memory consolidation / reflection pass** — periodic LLM-summary of episodic → semantic (B02, C11).
- **Importance scoring** — `importance: float` payload + recency-weighted recall (B02, C08).
- **Cross-conversation user profile** — SQLite `user_profile(user_id, field, value)` (C07, C11). Direct enabler for adaptive difficulty in quiz/path.

**Proposal — track M**: P0 fix B10 (persist chat to SQLite); P0 token-aware truncation; P1 episodic/semantic/procedural namespacing; P2 user_profile + adaptive difficulty.

---

### 5. LLM router

**Now**: `llm/router.py` — OpenAI vs DeepSeek by `"deepseek"` prefix. Static `_PROVIDERS` registry.

**Gaps** (`B7`, code §6):
- `ModeSpec.model` ∈ `{nano, pro, pro_vision}` is **not** wired to router — orchestrator passes `req.model` directly. Tier name unused except for vision-mode string match.
- No fallback on 5xx.
- No cost logging for the main stream (B7) — `stream_options={"include_usage": True}` never set.
- New `OpenAIChat()` instance per request → new httpx pool.
- Uniform `temperature=0.2` even for structured-output modes that want determinism.

**Literature upgrades** (synopsis §15):
- **Per-mode model rubric** — `ModeSpec.model_tier`; cheap for classifiers, expensive for synthesis (A03, C02, B10).
- **Cascade routing** — nano → escalate to pro on low confidence (B10).
- **No-retrieve short-circuit** — meta queries skip retrieval (P08, A06).
- **Ollama / LM Studio fallback provider** — local model behind env flag (C02, P02).
- **Smaller embed for query side** — `text-embedding-3-small` for HyDE/multi-query only (A03, P05).

**Proposal — track L**: P0 wire `ModeSpec.model` to router; P0 `stream_options.include_usage=True` + cost logging; P1 cascade router; P2 local fallback.

---

### 6. Mode registry & ModeSpec

**Now**: 11 modes registered at import. `ModeSpec` frozen dataclass.

**Gaps** (`B3`, `B4`, code §7):
- Dead fields: `tools`, `max_tool_calls`, `few_shot`, `post_validators`, `adjacent_sections`, `icon` (backend-side).
- `ModeRegistry._registry` is class-level mutable global — test isolation risk.
- Mixes orchestration (`memory`, `arch`) with declarative metadata.

**Literature upgrades** (synopsis §13):
- **Persona dataclass** — `system_prompt + few_shot + schema + tool_list` as a unit (C07).
- **Versioned prompts** — `prompts/<mode>/v<N>.txt` + eval-score per version (C09).
- **`ModeSpec.cot=True/False`** — CoT toggle per mode (A03, C10).
- **`ModeSpec.latency_budget_ms` / `cost_cap_usd`** (B02, B10).

**Proposal — track S**: P0 delete dead fields OR wire them; P1 promote `ModeSpec` → `Persona` with versioned prompts; P2 budget fields.

---

### 7. Schema validate + repair (ADR-005)

**Now**: `_validate_and_repair` — fence-strip → Pydantic validate → one repair LLM call → validate again → emit `SchemaValidationError` SSE on second failure.

**Gaps** (`B6`, code §8):
- Fence-strip breaks (B6).
- `except (ValidationError, Exception)` catches all programmer errors.
- Repair uses streaming + same temperature — no determinism bump.
- TutorAnswer hardcoded as skip sentinel.

**Literature upgrades** (synopsis §14):
- **OpenAI `response_format=json_schema` constrained decoding** — ≈ eliminates repair retries (C03, P02, U5). Massive cost + latency win.
- **Outlines / grammar-constrained decoding** for non-OpenAI providers (P02).

**Proposal — track V**: P0 switch to native `response_format=json_schema` for OpenAI providers; P0 fix fence-strip; P1 grammar-constrained decode for DeepSeek/Ollama.

---

### 8. Multi-agent runner (StateGraph)

**Now**: `agents/graph.py` — linear async pipeline, iter cap, one-step retry-on-fail.

**Gaps** (`B8`, code §9):
- Not a graph — no conditional edges, no fan-out, no parallel sub-runs.
- `qc_status` retry has logic hole — never re-set if retry exception (B8).
- `AgentState` is god-object dict; `extras` is stringly-typed (`sub_goals`, `weeks`, `cycles_broken`) — typo → silent `[]`.
- No streaming inside multi-agent runs — users wait silently.

**Literature upgrades** (synopsis §7, §8, §18):
- **Supervisor / QC node** — generic end-of-graph validator (schema + citation + faithfulness) (B08, C04).
- **Clarification node** — emit `clarify_request`, pause graph (B08, C11).
- **Streaming intermediate steps** — `agent_step` SSE events with node + status (B08, P08, U7).
- **Behavior-tree tick-status semantics** — success/fail/running per node for deterministic retry (C06).
- **Plan-and-solve / HuggingGPT 4-step** pattern as explicit graph shape (A09, C11).
- **Role-play / debate sub-graph** for research mode (pro-claim, con-claim, judge) (C04, A09).

**Proposal — track G**: P0 fix qc retry hole; P0 `agent_step` SSE streaming; P1 QC node + clarification node; P2 debate sub-graph for research.

---

### 9. Per-mode agent graphs (prereqs, research, study_path)

**Now**: 3 graphs in `agents/`. All call nano model directly. Best-effort KG persist (prereqs only).

**Gaps** (code §10):
- **prereqs**: fence-strip bug; `build_dag` silently drops invalid edges; LLM emits `from_id/to_id` but parser expects `from/to` (schema mismatch).
- **research**: serial per-claim retrieval (8× latency); stance "majority vote" is actually max-confidence non-background (docstring lies).
- **study_path**: sub-goals truncated to 7 silently; `invoke_prereqs_subgraph` runs full prereqs graph sequentially per sub-goal (7× retrieval + 7× extract + 7× build_dag); `StudyWeek.goals` field never populated; coverage threshold 0.4 hardcoded.
- All three graphs use nano regardless of `ModeSpec.model="pro"`.
- KG persistence only from prereqs (research/path don't persist).

**Literature upgrades** (synopsis §7, §8, §16):
- **Reflexion** — `path` mode writes reflection note on user deviation; used as prompt context next replan (C10, C11).
- **Self-RAG** wrapper for research/annotate — special tokens deciding retrieve / relevant / grounded (P08, C10).
- **Corrective RAG (CRAG)** — retrieval evaluator gate + auto-rewrite (A06, P08).
- **Adaptive RAG** — no-retrieve / single-step / multi-step classifier (A06, P08).
- **Goal calibration via clarification** in path/roadmap (B08, C11).
- **Spaced-repetition queue** — `review_queue(user_id, concept_id, next_due_at)` (C11).

**Proposal — track A**: P0 fix schema mismatch + dead JSON parse; P0 parallelise per-claim retrieval (`asyncio.gather`); P1 self-RAG wrapper for research; P2 reflexion for path replan.

---

### 10. Vision gate + inspect_figure

**Now**: gate w/ thresholds (0.62/0.45/3 max calls). Hardcoded to `req.mode in ("figures", "math")`.

**Gaps** (code §12):
- `VisionGateConfig` mode-specific overrides documented but never applied (default config always).
- String-coupled mode detection.
- Local file URLs skipped (only http).
- Vision notes appended *after* sources in system prompt → low-score figure can dominate.

**Literature upgrades** (synopsis §11):
- **CLIP joint embeddings** for figures — text-query → image hit without caption (B04, P03). Big win when caption sparse.
- **VLM-generated captions at ingest** — replace OCR-only (P03, B04).
- **Crop + re-inspect chain** for math figures (B04, P03).
- **Vision-aware rerank** when caption-rerank confidence low (B04).

**Proposal — track F**: P0 wire mode-specific gate overrides; P1 CLIP embeddings; P2 VLM caption ingest (ingestion-side).

---

### 11. KG persistence (concepts_kg)

**Now**: Qdrant collection w/ MD5(label)-derived IDs. Edges encoded as `payload["edges_out"]` on source node.

**Gaps** (code §11):
- Edges not merged on upsert — second prereqs run overwrites first's edges.
- `fetch_concepts_by_label` exists but never called → dead code.
- MD5 of label only — concept-id collisions on same label.
- Best-effort, silent failure.

**Literature upgrades** (synopsis §9):
- **Microsoft GraphRAG community summaries** — Leiden clustering + per-community summaries (A07, P09). Fit: roadmap, navigate big-picture.
- **HippoRAG / personalized PageRank** seeded on query entities (A07, P09). Fit: prereqs, compare.
- **Entity linking on query** — pre-retrieval NER → KG-canonical IDs (A07, P09). Critical for cross-book vocabulary mismatch.
- **Graph-augmented prompt context** — render KG neighborhood as mermaid/bullets, append to system prompt (P09).

**Proposal — track KG**: P0 fix edge overwrite on upsert; P1 entity-linking pre-step; P2 community summaries (background job).

---

### 12. SSE orchestrator + token-stream parsing

**Now**: `_process_stream` state machine for `\n\n` → `paragraph_break` and `$$...$$` → `math_block`. Accumulating wrapper for post-stream validation.

**Gaps** (code §15):
- Inline `$...$` not parsed (tutor prompt instructs inline math).
- Accumulator + token-stream divergence — math-block events fire mid-JSON if model emits `$$` inside a field value.
- Figure events emitted before `meta` — breaks documented order.
- Multi-agent modes: no streaming.

**Literature upgrades** (synopsis §18):
- **Partial-JSON streaming** for structured modes — emit `partial_json` events parseable by tolerant parser (B04, P02).
- **`agent_step` events** for multi-agent (U7).
- **CoT redaction** — `<thinking>` → separate SSE channel (C10).

**Proposal — track O**: P0 streaming events for multi-agent (`agent_step`); P1 partial-JSON streaming; P2 CoT redaction channel.

---

### 13. API surface (FastAPI)

**Now**: `/api/chat` SSE, `/api/study_plans/*`, mounted routers for books/retrieval/llm/store.

**Gaps** (`B10`, code §16):
- Chat path never persists user/assistant messages to SQLite (B10 root).
- CORS wildcard.
- No request ID flowing through pipeline.
- No timeouts on LLM calls.
- No rate limiting.
- `/replan` and `/section/{ref}` bypass conversation auth.

**Literature upgrades** (synopsis §20):
- **`slowapi` rate limiter** (B07).
- **Structured error envelope** + healthcheck w/ Qdrant + OpenAI reachability (B07).
- **Container hardening** — non-root, read-only FS (B07, P11).

**Proposal — track P (production)**: P0 fix B10; P0 request ID + LLM timeouts; P1 rate limiter + structured errors; P2 container hardening.

---

### 14. Per-mode prompts

**Now**: 11 prompt modules; orchestrator uses `INSTRUCTIONS` constant + appends sources w/ typo `REGRIEVED CONTEXT`.

**Gaps** (code §17):
- Every non-tutor `build_prompt(sources)` helper is **dead** — orchestrator appends sources itself.
- Prompts for `prereqs`/`research`/`path` are **dead** — multi-agent path bypasses LLM-as-prompted-JSON entirely.
- Typo `REGRIEVED` leaks into outputs.
- Tutor citation format diverges from other modes (`**Book (chapter, section)**` vs `{book, chapter, section}`).

**Literature upgrades** (synopsis §13):
- **Per-mode few-shot bank** — `prompts/<mode>/few_shot.jsonl`, sample by query similarity (A03, C02, P02). Direct wins: quiz, math, research.
- **CoT toggled per mode** (A03, C10).
- **Self-consistency / N-sample voting** for quiz (C10).
- **Self-critique loop** for research, annotate (C10, B08).
- **Versioned prompts** (C09).

**Proposal — track PR (prompts)**: P0 delete dead `build_prompt` helpers + fix typo; P0 unify citation format; P1 few-shot bank; P2 prompt versioning + per-version eval.

---

### 15. Output schemas

**Now**: 11 Pydantic v2 schemas + shared `Citation`, `FigureRef`.

**Gaps** (code §18):
- `ConceptEdge` field-name divergence (`from_id`/`to_id` vs LLM `from`/`to`).
- `Annotation.position: tuple[int, int]` — LLM unreliable for tuple shape.
- `StudyWeek.goals` never populated.
- `FigureRef.vision_used`/`vision_answer` never set.
- `Question.self_check_passed` defaults True — no actual self-check.

**Literature upgrades**: see Section 7 (constrained decoding).

**Proposal — track SC**: P0 align ConceptEdge field names; P0 populate StudyWeek.goals; P1 wire vision_used flag; merge into track V.

---

### 16. LangChain coupling

**Now**: `grep langchain src/services/chat/**` → 0 hits. ADR-001 satisfied. LangChain present in `src/ingestion/` only.

**Risk**: ADR-001 will be tested the moment tool-use lands — `langchain_core.tools` + `AgentExecutor` is the obvious shortcut.

**Proposal — track CW**: P1 add CI test that asserts `langchain` not in `sys.modules` after importing `src.services.chat`.

---

### 17. Evaluation

**Now**: 4 metrics in eval harness (feature 21). 212 backend tests.

**Gaps**: synopsis §12 — no synthetic test set, no Ragas, no nightly CI, no observability spans.

**Literature upgrades** (synopsis §12):
- **Synthetic test-set generation** from `data/parsed/manifest.json` (B05, P10).
- **Ragas full metric suite** — context precision/recall, faithfulness, answer relevance (B05, B06).
- **Eval-as-CI nightly** w/ baseline comparison + alert on Δ drop (B06, C09).
- **Prompt versioning + per-version eval** (C09).
- **Trace / span store** — `runs`, `spans`, `events` tables; replaces vision-only cost log (B06).

**Proposal — track E**: P0 trace store (replaces cost log); P0 synth test set; P1 Ragas integration; P1 nightly CI eval.

---

### 18. Production concerns

**Literature upgrades** (synopsis §20):
- **Embedding cache** SQLite-backed (A10, B06).
- **Result cache** per `(mode, query_hash, book_set)`, TTL'd (A10).
- **Latency budget per mode** (B02, B10).
- **Cost cap per turn + per session** (B02, B10).

**Proposal — track C (cache+cost)**: P1 embedding cache; P1 result cache (per-mode TTL); P2 budgets + caps.

---

## Proposed upgrade tracks (priority-ranked)

Four phases. Each phase = self-contained, ship-able milestone.

### Phase 1 — Stop the bleeding (P0 bugs)

| Track | Items | Effort |
|-------|-------|--------|
| **Persistence** | Fix B10 (write chat history to SQLite); fix B7 (cost log on main stream + agent nodes); fix B1 (request IDs) | M |
| **Retrieval correctness** | Fix B5 (cross-collection RRF); wire `adjacent_sections` flag; pass `chunk[:2000]` to reranker | M |
| **Query correctness** | Fix B2 (real LLM rewriter); fix B6 (fence-strip + substring strip) | M |
| **Tool-surface honesty** | Delete dead `tools[]` / `max_tool_calls` / `few_shot` / `post_validators` / dead `build_prompt` helpers; fix typo `REGRIEVED` | S |
| **Multi-agent fix** | Fix B8 (qc retry hole); align `ConceptEdge` field names; parallelise per-claim retrieval | M |
| **Validation** | Switch OpenAI providers to `response_format=json_schema` (U5) | S |

**Total: P0 bug fixes + ADR-005 simplification. Roughly 1-2 sprints.**

### Phase 2 — Faithfulness + UX (high-trust differentiators)

| Track | Items | Effort |
|-------|-------|--------|
| **Faithfulness** | NLI-based citation verification (U1); CoVe loop behind `verify_pass` flag; supervisor QC node | L |
| **Streaming multi-agent** | `agent_step` SSE events (U7); partial-JSON streaming for structured modes | M |
| **Adaptive routing** | Query classifier + adaptive RAG (U6); no-retrieve short-circuit; cascade routing | M |
| **Eval** | Trace store; synth test set; Ragas integration; nightly CI eval | L |

### Phase 3 — Longitudinal tutor (memory + personalization)

| Track | Items | Effort |
|-------|-------|--------|
| **Memory** | Episodic/semantic/procedural namespacing; consolidation pass; importance scoring (U3) | L |
| **Profile** | `user_profile` SQLite table; adaptive difficulty in quiz/path; review_queue for spaced-repetition | M |
| **Retrieval depth** | Hypothetical-question index (U2); parent-document retrieval; cross-collection RRF fusion | L |
| **Clarification** | `clarify_request` SSE event + pause/resume; goal calibration in path/roadmap | M |

### Phase 4 — Agentic + KG (advanced)

| Track | Items | Effort |
|-------|-------|--------|
| **Real tool-use** | Function-calling wired in OpenAI client; `retrieve` / `recall` / `commit` / `inspect_figure` as actual tools (U4); MCP server export | L |
| **KG upgrades** | Entity linking on query; community summaries; HippoRAG | L |
| **Vision-RAG** | CLIP embeddings on `<field>_images`; vision-aware rerank; VLM caption ingest | L |
| **Advanced reasoning** | Self-RAG wrapper; CRAG retrieval evaluator; debate sub-graph for research; reflexion for path replan | L |

---

## Open questions to discuss

Before proposing a concrete next-task, decide:

1. **Phase ordering** — agree Phase 1 → 2 → 3 → 4, or reorder? E.g. do you want faithfulness (Phase 2 U1) before persistence fixes?
2. **Tool-use commitment** — Phase 4 U4 (real function calling) is the biggest architectural decision. Alternative: delete `tools[]` entirely and stay one-shot RAG. Which?
3. **Scope of "compare" fix** — quick win: per-book retrieval (Phase 1, retrieve_per_book becomes real). Deep win: cross-collection RRF fusion + MMR (Phase 3). Both?
4. **Eval first vs. fix first** — synth test set + Ragas (Phase 2 track E) gives regression safety. Run before any other phase, or accept risk?
5. **Multi-agent expansion** — keep 3 modes (prereqs/research/path) or add more (e.g. compare as multi-agent with per-book workers + synthesizer)?
6. **Local fallback** — Ollama/LM Studio register in router? Yes = cost win + offline; no = simplicity.
7. **Prompts as a separate package** — promote `prompts/` to versioned per-mode files with eval-scores per version, or leave inline?

---

## Source files

- `.audit_code_chat.md` — full code audit, 22 features, file:line refs throughout
- `.audit_synopsis_chat.md` — 21 topic areas, 43 synopsis sources cross-referenced
- `docs/services/chat-features/README.md` — current 29-feature index
- `docs/services/modes/README.md` — per-mode developer documentation
- `docs/upgrades/Chat/implementation_plan.md` — original M1-M10 plan; ADR-001/005 trade-offs documented
