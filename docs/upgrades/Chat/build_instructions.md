# Build Instructions — Chat RAG System

> Step 3 deliverable (Pass-2 revision). Source: distillation of `abstract.md` (11 services) cross-referenced w/ 43 chapter synopses + verified against current code in `src/services/chat/`. Read `control.md` first.
>
> **Revision notes (Pass 2)**: mode IDs aligned to existing `schemas.py::ModeId` Literal; multi-agent modes no longer expose graph nodes as LLM tools; post-process validators separated from tool registry; vision gate simplified to single-score (caption) since `Figure` schema lacks image score; query-expansion LLM hops added to cost accounting; iter caps reconciled.

---

## 1. Backbone restated

Canonical request flow per mode. Each stage cites synopsis evidence.

```
User input + mode_id (from ChatRequest)
   ↓
[1. Mode loader]              ← ModeRegistry.get(mode_id) → ModeSpec       (C7)
   ↓
[2. Memory injector]          ← MemoryStrategy.build_context(conv_id, q)   (C8, B2)
   ↓
[3. Query processor]          ← rewrite, expand, HyDE, multi-query         (P7, A6, B2)
   ↓
[4. Hybrid retriever]         ← dense (3-large) + sparse (bm25) RRF fusion (B3, B4, A6)
   ↓
[5. Reranker]                 ← cross-encoder top-50 → top-10              (A6, P7, B4)
   ↓
[6. Context assembler]        ← dedup, adjacent expand, token budget       (A6, B2, A2)
   ↓
[7a. Single-agent: tool loop] ← LLM + tools, ≤max_tool_calls               (P8, C5)
[7b. Multi-agent: graph]      ← state machine (modes 6, 8, 10)             (B8, A9, C4)
   ↓
[8. Output formatter]         ← schema validation + 1 schema-repair retry  (C9)
   ↓
[9. Post-process validators]  ← self_check / latex_check / cycle_check     (C10)
   ↓
[10. Citation block]          ← {book, chapter, section, page, chunk_id}  (A3, A5)
   ↓
[11. SSE emitter]             ← token, meta, source_chip, …, done         (existing)
```

**Backbone holds for every mode.** Modes differ in: persona prompt, output schema, tool list, retrieval flags, model tier.

Current code maps to: stage 3 = `chat/rewriter.py`; stage 4 = `chat/retrieval.py`; stage 7a (no tools yet) = `chat/orchestrator.py`; stage 11 = SSE in `orchestrator.py`. **Missing: stages 1, 2, 5, 6 (assembler proper), 7b, 8, 9.**

---

## 2. Per-mode persona template

Target file layout:
- `src/services/chat/modes.py` — `ModeRegistry` (11 specs)
- `src/services/chat/prompts/<mode>.py` — system prompt + few-shot per mode
- `src/services/chat/schemas/output.py` — Pydantic output models
- `src/services/chat/tools/<tool>.py` — tool handlers (single-agent only)
- `src/services/chat/agents/<mode>.py` — state graphs (multi-agent only)

### 2.1 ModeSpec dataclass

```python
@dataclass(frozen=True)
class ModeSpec:
    id: ModeId                       # matches schemas.py::ModeId Literal
    icon: str
    arch: Literal["single", "multi"] # routes to stage 7a vs 7b
    system_prompt: str
    few_shot: list[Example]          # 0..3
    output_schema: type[BaseModel]
    tools: list[Tool]                # empty for multi-agent
    retrieval_flags: RetrievalFlags
    model: ModelTier                 # nano | pro | pro_vision
    max_tool_calls: int = 3          # single-agent only
    max_graph_iters: int = 12        # multi-agent only (per-mode override below)
    post_validators: list[str] = ()  # names of post-process checks
    memory: Literal["off", "sliding", "summary", "vec", "auto"] = "off"
```

`RetrievalFlags`:
```python
@dataclass
class RetrievalFlags:
    rewrite: bool = True
    hyde: bool = False
    multi_query: int = 0     # 0 = off, ≥2 = N variants
    decompose: bool = False
    rerank: bool = True
    adjacent_window: int = 0 # 0 = off, 1 = ±1 chunk
    metadata_filters: tuple[str, ...] = () # extra payload keys allowed
```

### 2.2 Mode table — 11 entries (IDs aligned to `schemas.py::ModeId`)

| # | id | arch | Tools (single only) | rewrite | hyde | multi_query | decompose | rerank | adjacent | Schema | Model | Validators | Mem |
|---|----|------|---------------------|---------|------|-------------|-----------|--------|----------|--------|-------|------------|-----|
| 1 | `tutor` | single | `retrieve` | yes | – | – | – | yes | 1 | `TutorAnswer` | nano | citation | auto |
| 2 | `compare` | single | `retrieve_per_book` | yes | – | 2 per book | – | yes | – | `Comparison` | pro | citation | sliding |
| 3 | `figures` | single | `retrieve`, `retrieve_figures`, `inspect_figure` | yes | – | – | – | yes | 1 | `FigureAnswer` | pro_vision | citation, vision_gate | sliding |
| 4 | `quiz` | single | `retrieve` | yes | – | – | – | yes | 1 | `Quiz` | nano | citation, self_check | off |
| 5 | `navigate` | single | `retrieve` | yes | yes | – | – | yes | – | `Locations` | nano | citation | off |
| 6 | `prereqs` | multi | – | yes | – | – | yes | yes | – | `DAG` | pro | citation, cycle_check | off |
| 7 | `annotate` | single | `extract_terms`, `retrieve` | yes | – | 2 per term | – | yes | – | `Annotations` | nano | citation | off |
| 8 | `research` | multi | – | yes | – | – | yes | yes | – | `Report` | pro | citation, stance_consistency | off |
| 9 | `math` | single | `retrieve`, `retrieve_figures`, `inspect_figure` | yes | – | – | – | yes | 1 | `MathAnswer` | pro_vision | citation, latex_check, vision_gate | sliding |
| 10 | `path` | multi | – | yes | – | – | yes | yes | – | `StudyPlan` | pro | citation, coverage_check | persist |
| 11 | `roadmap` | single | `retrieve` | yes | – | 3 | yes | yes | – | `Roadmap` | pro | citation, yaml_schema | off |

Notes:
- `self_check`, `latex_check`, `cycle_check`, `validate_schema`, `coverage_check`, `stance_consistency` are **post-process validators** (stage 9), not LLM-callable tools.
- Multi-agent modes (6, 8, 10) have empty `tools` list; their graph nodes are not LLM-exposed (deterministic Python).
- `memory="auto"` escalates sliding → summary → vec by turn count (§4.1).
- `pro_vision` = `gpt-4o` (vision-capable); falls back to `pro` when vision not triggered.

### 2.3 System prompt skeleton (all modes)

```
You are <persona>. You answer ONLY from retrieved context provided below.

HARD RULES:
1. Every factual claim cites {book, chapter, section, chunk_id}.
2. If context insufficient: respond "Insufficient evidence in indexed corpus" + bullet list of what's missing.
3. Do not invent definitions, theorems, notation, or page numbers.
4. Output MUST validate against schema <SchemaName>; output JSON only when schema-mode active.
5. <mode-specific rules>

RETRIEVED CONTEXT:
<assembled chunks with [SRC i] tags>

MEMORY (if any):
<prior-turn excerpts>

USER QUERY:
<query>
```

Source: A3 (citation discipline), A5 (hallucination mitigation), C7 (persona class).

---

## 3. Retrieval upgrades (Phase 2)

Add as composable layers w/ flags per mode (`RetrievalFlags`).

### 3.1 Reranker (priority 1)

- Model: `BAAI/bge-reranker-v2-m3` (local; via `sentence-transformers`). Confirm w/ user (§10).
- Position: after RRF fusion, before context assembly.
- Input: query + top-50 from fusion. Output: top-10 by cross-encoder score.
- API change: `retrieval.hybrid_search()` accepts `rerank: bool, rerank_top_n: int`.
- Code: new `chat/rerankers.py::CrossEncoderReranker` (lazy load on first call).
- Source: A6, P7, B4.

### 3.2 HyDE

- LLM (nano) generates hypothetical passage → embed → retrieve dense path only.
- Flag: `flags.hyde=True` (default for `navigate`).
- Code: `chat/query_expansion.py::hyde(q, model) -> str`.
- Cost: +1 nano completion + 1 embedding per query.
- Source: P7, A6.

### 3.3 Multi-query

- LLM rewrites q into N variants. Retrieve each, union, dedup by `chunkId`, then rerank.
- Flag: `flags.multi_query=N` (0 = off).
- Cost: +1 nano completion + N retrievals per query.
- Source: P7, B4.

### 3.4 Metadata filter

- Already in code (`book_slug`). Extend to `chapter_id`, `section_path`, `figure_only`.
- Filters declared per mode via `flags.metadata_filters`; values come from `ChatRequest.book_filter` + mode-specific defaults.
- Source: P4, P7.

### 3.5 Query decomposition

- For complex prompts (modes 6, 8, 10, 11). Split into atomic sub-queries.
- LLM (pro) returns JSON `{sub_queries: list[str]}`.
- Flag: `flags.decompose=True`.
- Cost: +1 pro completion per query.
- Source: P7, A9.

### 3.6 Context enrichment (adjacent chunks)

- After rerank: for each surviving chunk, pull chunks w/ `chunk_index ∈ [i-W, i+W]` AND same `(book_slug, chapter_id, section_path)`.
- Verified `chunk_index` exists in payload (`src/ingestion/build_documents.py:119`).
- Configurable via `flags.adjacent_window` (default 0; tutor/figures/quiz/math = 1).
- Token-budget gate: drop adjacent if assembled context would exceed budget.
- Source: A6.

### 3.7 Stage order (canonical)

```
q
 → rewrite                            (if flags.rewrite)
 → [hyde] | [multi_query → N qs] | [decompose → K sub_qs]   (mutually compatible)
 → for each q_variant: hybrid_search (dense + sparse) → fuse via RRF
 → union all variants → dedup by chunkId
 → rerank (cross-encoder)
 → adjacent_expand (if window > 0)
 → token-budget trim
```

---

## 4. Memory architecture

Two namespaces; never mixed.

| Namespace | Collections | Lifetime | Strategy |
|-----------|-------------|----------|----------|
| **Knowledge** | `<field>_textbooks`, `<field>_images` | permanent | read-only; current code |
| **Memory** | `conv_<conversation_id>` (created lazily) | per-conv; deleted on conv delete | sliding / summary / vec |

### 4.1 Strategy switch (auto-escalation)

| Strategy | Trigger | Mechanism | Token cost |
|----------|---------|-----------|------------|
| `sliding` | turns ≤ 10 | last 10 messages verbatim | low |
| `summary` | 10 < turns ≤ 30 | LLM (nano) compresses oldest 50% into 1 paragraph; keep recent 50% verbatim | +1 nano on overflow |
| `vec` | turns > 30 | embed each prior turn → `conv_<id>` collection; retrieve top-5 per new query | +1 embed/turn + 1 retrieval/query |

Thresholds chosen so:
- Sliding fits in 8k-token budget at avg 400 tok/turn × 10 = 4k.
- Summary kicks in before context overflow on pro models.
- Vec only when sliding+summary would still overflow.

Code: `chat/memory.py::MemoryStrategy.build_context(conv_id, query, mode_spec) -> MemoryContext`.

Source: C8 (knowledge vs memory split), B2 (sliding/summary/vec).

### 4.2 Wiring

- `ModeSpec.memory` selects: `off | sliding | summary | vec | auto | persist`.
- `auto` follows §4.1 table.
- `persist` (mode 10 only): plan state to SQLite `study_plans`; conv messages also sliding.
- `conv_<id>` collection created on first `vec` write; vector dim = 3072 (matches embedding).
- `DELETE /api/conversations/{id}` triggers Qdrant collection delete (best-effort, log on fail).

---

## 5. Multi-agent shape

State-machine pattern. Modes 6, 8, 10. **Roll own** minimal runner (≤300 LoC; no LangGraph dep) — confirm w/ user (§10).

### 5.1 Shared state schema

```python
@dataclass
class AgentState:
    conv_id: str
    mode: ModeId
    user_input: str
    memory_context: str | None
    intent: dict | None              # populated by clarify/decompose
    sub_queries: list[str]           # if decomposed
    retrieval_results: list[Chunk]   # union across sub_queries
    figures: list[Figure]            # for vision-capable modes (future-proof)
    drafts: dict[str, Any]           # per-node outputs (claims, dag, etc.)
    qc_status: Literal["pending", "pass", "fail"]
    qc_reasons: list[str]
    citations: list[Citation]
    errors: list[str]
    iter: int                        # incremented per node visit
    cost_log: list[dict]             # {step, model, tokens, vision_used, usd}
```

### 5.2 Generic nodes (composable; deterministic Python — not LLM tools)

| Node | Input | Output | Used by |
|------|-------|--------|---------|
| `clarify` | user_input | intent OR clarifying_question (LLM) | 10 |
| `decompose` | intent | sub_queries (LLM) | 6, 8, 10 |
| `retrieve` | sub_queries | retrieval_results | all |
| `extract_concepts` | retrieval_results | concept set (LLM) | 6 |
| `extract_claims` | user_input (paper excerpt) | claims (LLM) | 8 |
| `classify_stance` | (claim, chunks) | SUPPORTS/CONTRADICTS/BACKGROUND (LLM) | 8 |
| `build_dag` | concepts + retrieval_results | DAG (LLM + Python) | 6, 10 |
| `cycle_check` | DAG | DAG (Python, deterministic) | 6, 10 |
| `sequence` | acyclic DAG | ordered list (topo sort) | 6, 10 |
| `validate_coverage` | plan + manifest | plan + gap list | 10 |
| `synthesize` | drafts | final draft (LLM) | 6, 8, 10 |
| `qc` | final + retrieval | pass/fail + reasons (LLM-judge) | 6, 8, 10 |
| `finalize` | final | schema-validated output | all |

### 5.3 Per-service graphs + iter cap

| Mode | Graph | Nodes | `max_graph_iters` |
|------|-------|-------|-------------------|
| 6 prereqs | `retrieve → extract_concepts → build_dag → cycle_check → sequence → synthesize → qc → [retry once if fail] → finalize` | 7 | 12 (allow 1 retry of decompose+retrieve) |
| 8 research | `extract_claims → decompose → retrieve(×claim) → classify_stance(×claim) → synthesize → qc → [retry once] → finalize` | 7 | 12 |
| 10 path | `clarify → decompose(goal) → invoke_subgraph(prereqs) → sequence → validate_coverage → finalize → persist` | 7 | 15 |

QC failure → 1 retry of upstream node max. Hard cap on graph iters; on cap hit emit partial + `error`.

### 5.4 Cross-mode invocation (mode 10 → mode 6)

`invoke_subgraph(prereqs)` runs the prereqs graph with shared `AgentState`. Same process, no HTTP. Result merged into `drafts["prereqs_dag"]`. Iter counter combined (counts toward path's `max_graph_iters=15`).

Persist mode-10 plan state in SQLite `study_plans(conv_id PK, state_json, updated_at)`. Replan node triggered by:
- explicit `POST /api/study_plans/{id}/replan`
- user deletion of a planned section via `DELETE /api/study_plans/{id}/section/{ref}`

Source: B8 (state-machine + clarify + supervisor), A9 (HuggingGPT 4-step), C4 (role-based crews).

---

## 6. Tool-calling channel (single-agent only)

Stage 7a. Multi-agent modes do not use this path.

### 6.1 Tool registry

```python
@dataclass
class Tool:
    name: str
    description: str
    parameters: type[BaseModel]   # JSON-schema for OpenAI / DeepSeek tool API
    handler: Callable[..., Awaitable[Any]]
```

Initial tool set (single-agent only):
- `retrieve(query, top_k, book_slugs?)` — hybrid retrieval
- `retrieve_per_book(query, slug)` — single-book retrieval (mode 2)
- `retrieve_figures(query, top_k)` — image collection (modes 3, 9)
- `inspect_figure(figure_id, question)` — vision call w/ gate (modes 3, 9)
- `extract_terms(text)` — noun-phrase extraction (mode 7)

Post-process validators (NOT tools, run after stage 8):
- `self_check(quiz_item, chunks)` — answerable from text? (mode 4)
- `latex_check(text)` — KaTeX-parse all `$...$` / `$$...$$` (mode 9)
- `yaml_schema(output)` — full YAML schema validation (mode 11)
- `vision_gate_check(figures)` — confirm gate respected (modes 3, 9)
- `citation` — every claim sentence has at least one `[chunk_id]` reference

### 6.2 Loop

```
messages = [system, memory_ctx, retrieved_ctx, user_query]
for iter in range(mode_spec.max_tool_calls + 1):
    response = await llm_call(messages, tools=mode_spec.tools)
    cost_log.append(response.usage)
    if not response.tool_calls or iter == mode_spec.max_tool_calls:
        return response.content
    for tc in response.tool_calls:
        result = await tools[tc.name].handler(**tc.args)
        messages.append({"role": "tool", "content": json.dumps(result), "tool_call_id": tc.id})
```

Iter cap = `max_tool_calls + 1` to allow one final answer pass after the last tool round.

Source: P8 (agentic-RAG loop), C5 (semantic + native functions).

---

## 7. Vision gate

Caption-first; image bytes only on gate.

### 7.1 Available signal

Current `Figure` payload (verified `retrieval.py:252-259`): `ref, book_slug, chapter_id, caption, url`. Only **one** score per figure: dense similarity of query embedding to caption embedding. There is no separate image-embedding score unless we add one (CLIP/SigLIP). Treat addition as out-of-scope for v1.

### 7.2 Algorithm (v1, single score)

```python
def vision_gate(figures, query) -> list[FigureRef]:
    out = []
    for f in figures[:5]:                       # cap N
        if f.score >= τ_high:                   # τ_high = 0.62
            out.append(FigureRef(figure=f, vision_used=False))   # caption suffices
        elif f.score >= τ_low:                  # τ_low = 0.45
            answer = await inspect_figure(f.ref, query)          # call gpt-4o
            cost_log.append({"figure": f.ref, "vision_used": True, "usd": cost})
            out.append(FigureRef(figure=f, vision_used=True, vision_answer=answer))
        # else drop
    return out
```

τ values are initial; calibrate against hand-labeled `data/eval/vision20.jsonl` (M8 gate, see `test_plan.md`).

### 7.3 v2 (out of scope unless user requests)

- Add CLIP/SigLIP image embedding at ingestion; expose `image_score` field; two-score gate.

Source: B4 strategy 2.

---

## 8. Output schemas

Every mode produces a Pydantic model that **must validate** before stream `done` event. Validation failure → 1 retry w/ schema-repair prompt; second failure → return partial + `error` SSE event.

### 8.1 Mandatory citation (every mode)

```python
class Citation(BaseModel):
    book: str                       # slug
    chapter: str                    # ch02
    section: str                    # "2.2.1"
    page_range: str | None = None
    chunk_id: str                   # for traceability + highlight
```

Every claim sentence MUST carry at least one citation reference resolvable to a `Citation` in the response's `citations` list.

### 8.2 Per-mode schemas

```python
class TutorAnswer(BaseModel):
    text: str
    citations: list[Citation]

class PerBookSection(BaseModel):
    book: str; text: str; citations: list[Citation]

class Comparison(BaseModel):
    per_book: list[PerBookSection]      # list preserves order; one per book in filter
    synthesis: str
    gaps: list[str]                      # asymmetric coverage notes
    citations: list[Citation]            # synthesis-level citations

class QuizQ(BaseModel):
    q: str
    rubric: str
    hints: list[str]
    difficulty: Literal["easy","med","hard"]
    citations: list[Citation]
    self_check_passed: bool             # set by post-validator
class Quiz(BaseModel):
    questions: list[QuizQ]

class LocationRef(BaseModel):
    book: str; chapter: str; section: str; score: float; snippet: str
class Locations(BaseModel):
    items: list[LocationRef]
    expanded_terms: list[str]            # for transparency

class DAGNode(BaseModel):
    id: str; label: str; citation: Citation
class DAGEdge(BaseModel):
    src: str; dst: str; weight: float = 1.0
class DAG(BaseModel):
    target: str                          # the queried concept
    nodes: list[DAGNode]
    edges: list[DAGEdge]
    order: list[str]                     # topo-sorted node ids
    cycles_broken: list[tuple[str, str]] = []

class Annotation(BaseModel):
    term: str
    definition: str
    citation: Citation                   # NOT optional (was a bug)
    in_corpus: bool = True
class Annotations(BaseModel):
    items: list[Annotation]
    not_in_corpus: list[str]             # terms with no library coverage

class ClaimResult(BaseModel):
    claim: str
    stance: Literal["SUPPORTS","CONTRADICTS","BACKGROUND"]
    evidence: list[str]                  # quoted snippets
    citations: list[Citation]
    confidence: float
class Report(BaseModel):
    claims: list[ClaimResult]
    coverage_gaps: list[str]
    overall_summary: str

class FigureRef(BaseModel):
    figure_id: str
    caption: str
    url: str
    vision_used: bool
    vision_answer: str | None = None
class FigureAnswer(BaseModel):
    text: str
    figures: list[FigureRef]
    citations: list[Citation]

class MathAnswer(BaseModel):
    text_with_latex: str
    figures: list[FigureRef]
    citations: list[Citation]
    latex_check_passed: bool

class Week(BaseModel):
    n: int
    sections: list[Citation]
    goals: list[str]
class StudyPlan(BaseModel):
    goal: str
    weeks: list[Week]
    total_weeks: int
    gaps: list[str]
    replanned_from_version: int | None = None

class Scene(BaseModel):
    id: int
    title: str
    concept: str
    source: Citation
    suggested_visual: str
    duration_hint: str
    figure: str | None = None
class Roadmap(BaseModel):
    topic: str
    target_audience: str
    total_duration_estimate: str
    scenes: list[Scene]
```

Code location: `src/services/chat/schemas/output.py`.

---

## 9. Cost tiers

Per-mode default model. Override via `ChatRequest.model_id`.

### 9.1 Tier definition (verified against `chat/llm/router.py`)

- `nano` = `gpt-5.4-nano-2026-03-17` ✓
- `pro` = `gpt-5.4-2026-03-05` ✓ OR `deepseek-v4-pro` (cheaper fallback)
- `pro_vision` = `gpt-4o` ✓ (vision-capable)
- Reasoner alt: `deepseek-reasoner` (for CoT-heavy modes if quality demands)

### 9.2 Per-mode tier

| Mode | Main model | Aux LLM hops | Cost notes |
|------|-----------|---------------|------------|
| tutor | nano | rewrite (nano), memory-summary (nano, occasional) | low |
| compare | pro | rewrite (nano), multi_query (nano) | medium |
| figures | pro_vision (gated) → pro fallback | rewrite (nano) | high when vision triggers |
| quiz | nano | self_check (nano) | low |
| navigate | nano | hyde (nano) | low |
| prereqs | pro | decompose (nano), extract_concepts (pro), qc (nano-judge) | medium-high |
| annotate | nano | extract_terms (nano), multi_query per term (nano) | low-medium (scales w/ #terms) |
| research | pro | decompose (nano), claim extraction (pro), stance per claim (pro), qc (nano) | high |
| math | pro_vision (gated) → pro fallback | rewrite (nano) | high when vision triggers |
| path | pro | clarify (pro), decompose (pro), invokes prereqs subgraph | highest |
| roadmap | pro | decompose (pro), multi_query (nano) | medium-high |

### 9.3 Cost log

Orchestrator and agent graph append per-LLM-call records to `data/cost_log.jsonl`:
```json
{"ts": "...", "conv_id": "...", "mode": "tutor", "model": "gpt-5.4-nano-2026-03-17",
 "stage": "main|rewrite|hyde|multi_query|decompose|memory_summary|tool|qc|vision",
 "prompt_tokens": 1234, "completion_tokens": 256, "vision_used": false, "usd_est": 0.0042}
```

`usd_est` computed from static price table in `chat/cost.py`.

Source: B6 (economics), C2 (model selection rubric).

---

## 10. Open decisions for user (must confirm before Step 5)

Defaults proposed; user may override.

1. **Reranker model** — `BAAI/bge-reranker-v2-m3` (local, free) ✅ default. Alt: `cohere/rerank-3` (API, paid).
2. **Vision model** — `gpt-4o` ✅ default. Alt: local LLaVA.
3. **Vision gate τ** — τ_high=0.62, τ_low=0.45 ✅ initial; recalibrate w/ `vision20.jsonl`.
4. **Ollama fallback** — defer to post-v1 (not in Phase 2 scope). ✅
5. **Eval cadence** — 50-question synthetic set (`base50.jsonl`), on-PR + nightly. ✅
6. **Multi-agent framework** — roll own state-graph runner (≤300 LoC). ✅ Alt: LangGraph.
7. **KG persistence (mode 6)** — Qdrant collection `concepts_kg` w/ payload `{from, to, weight, source_citation}`. ✅ Alt: NetworkX + SQLite.
8. **Memory namespace TTL** — delete `conv_<id>` collection on `DELETE /api/conversations/{id}`; no time-based TTL. ✅
9. **Reranker hosting** — in-process via `sentence-transformers` (lazy load). ✅ Alt: separate microservice.
10. **Image embedding (v2 vision gate)** — defer until v1 measured insufficient. ✅
11. **Pro model resolution** — `gpt-5.4-2026-03-05` for OpenAI tier; `deepseek-v4-pro` accepted as override. ✅
12. **Coverage gap detector (mode 10)** — heuristic = goal sub-topic w/ zero high-rerank hits across all books. Confirm acceptable.

Block Step 5 until user confirms (or accepts defaults).

---

## Triple-check log (Pass 2)

- ✅ Mode IDs aligned to existing `schemas.py::ModeId` Literal.
- ✅ Tools vs validators vs graph nodes cleanly separated.
- ✅ `chunk_index` payload verified present (`build_documents.py:119`).
- ✅ Vision gate algorithm uses only available `Figure.score`; v2 image-score deferred.
- ✅ Multi-agent iter cap reconciled w/ §5.3 per-mode budgets.
- ✅ `pro` and `pro_vision` model IDs verified against `router.py`.
- ✅ Cost accounting includes auxiliary LLM hops (rewrite, hyde, multi_query, decompose, memory_summary, qc).
- ✅ Open decisions expanded from 8 → 12 (coverage detector, image embed v2, pro model resolution added).
