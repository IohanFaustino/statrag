# Test Plan — Chat RAG System

> Step 4b deliverable (skill-driven rewrite). Aligned to `implementation_plan.md` milestones. Source: `control.md §8` + P10 (eval) + B5 (Ragas) + B6 (observability) + C9 (prompt regression).
>
> Each test type is a **self-contained ticket** w/ files, code snippets, and acceptance gates. Test-types ↔ milestones table at end maps every milestone to required tests.

---

## 0. Test pyramid

```
        T7 (perf) · T11 (synth-gen)
       /                              \
      T3 T4 T5 (LLM-judge, regression)
     /                                  \
    T2 T6 T8 T9 T10  (retrieval / agents / vision / memory)
   /                                       \
  T1 (smoke)  +  existing 61 unit tests
```

Cheap tests run on every PR. Expensive (LLM-judge, perf) nightly + on milestone exit.

---

## 1. Layout

```
src/services/chat/tests/         # pytest unit + integration
src/services/eval/               # offline eval harness (built in M4)
data/eval/
  ├── base50.jsonl               # synthetic Q/A (M4 bootstrap)
  ├── stance20.jsonl             # hand-labeled stance triples (M6 gate)
  ├── vision20.jsonl             # hand-labeled (q, figure, vision_needed) (M8 gate)
  ├── navigator15.jsonl          # vocab-mismatch queries w/ gold location (M3 gate)
  ├── quiz10.jsonl               # vetted answerable quiz items (M2 sanity)
  ├── baselines.json             # frozen metric floors per metric × mode
  └── reports/<date>_<mode>_<set>.json
```

Pytest entry: `.venv/bin/python -m pytest src/services/chat/tests/ -v`.

Eval CLI: `.venv/bin/python -m src.services.eval.runner --set base50 --mode <mode>`.

---

## 2. NFR ↔ test mapping

| NFR | Tests covering it |
|-----|-------------------|
| NFR1 (p95 single ≤8s) | T7 |
| NFR2 (p95 multi ≤25s) | T7 |
| NFR3 (faithfulness ≥0.85) | T3 |
| NFR4 (context precision @10 ≥0.65) | T2 |
| NFR5 (citation 100%) | T6 |
| NFR6 (coverage ≥80% in chat/) | pytest --cov gate |
| NFR7 (Chinese-wall) | T1 grep check |
| NFR8 (backcompat) | existing 61 tests in T1 set |
| NFR9 (cost log) | T7 + T9 cost assertions |
| NFR11 (schema valid 100%) | T6 schema-valid count |
| NFR12 (mem cleanup) | T10 conv-delete assert |

---

## 3. Test types

### T1 — Tool integrity (smoke)

**Verifies**: API/Qdrant/LLM/SSE all responding; Chinese-wall preserved; backcompat.

**Files**:
- `tests/test_api_smoke.py` — already exists; extend w/ 11-mode dispatch ping.
- `tests/test_sse_smoke.py` — assert event order: `meta → ≥1 token → done`.
- `tests/test_chinese_wall.py` — grep `from src\.(ingestion|services\.(retrieval|eval))` in `src/services/chat/` returns empty.

**Snippet**:
```python
@pytest.mark.parametrize("mode", ["tutor","compare","figures","quiz","navigate",
                                  "prereqs","annotate","research","math","path","roadmap"])
def test_dispatch_each_mode(client, mode):
    r = client.post("/api/chat", json={"mode": mode, "query": "test"})
    assert r.status_code == 200
    events = parse_sse(r)
    assert events[0]["event"] == "meta"
    assert events[-1]["event"] == "done"
```

**Cadence**: every PR. **Gate**: 100% green.

**Source**: existing tests + B7.

---

### T2 — Retrieval relevance

**Verifies**: gold chunk in top-k; context precision/recall on `base50`.

**Files**:
- `tests/test_retrieval_relevance.py`
- Calls `src.services.eval.metrics.context_precision_at_k`, `context_recall_at_k`.

**Snippet**:
```python
def test_recall_at_10_base50():
    qs = load_jsonl("data/eval/base50.jsonl")
    hits_per_q = [hybrid_search(q.text, top_k=10, rerank=True) for q in qs]
    recall = sum(any(h.chunkId == q.gold_chunk_id for h in hits)
                 for hits, q in zip(hits_per_q, qs)) / len(qs)
    assert recall >= 0.80   # regression gate
```

**Cadence**: nightly + on retrieval/rerank changes. **Gate**: ≥0.80 recall @10; precision baseline frozen in `baselines.json`.

**Source**: P10, B5, A5.

---

### T3 — Faithfulness (LLM-judge)

**Verifies**: claims in answer supported by retrieved chunks.

**Files**:
- `tests/test_faithfulness.py`
- Uses `src.services.eval.metrics.faithfulness(answer, contexts, judge_model)`.

**Snippet**:
```python
async def test_faithfulness_tutor_base50():
    qs = load_jsonl("data/eval/base50.jsonl")
    scores = []
    for q in qs:
        out = await run_mode("tutor", q.text)
        scores.append(await faithfulness(out.text, out.contexts, "gpt-5.4-nano-2026-03-17"))
    assert mean(scores) >= 0.85   # NFR3
```

**Cadence**: nightly + on prompt/router changes. **Gate**: mean ≥0.85.

**Source**: P10, B6.

---

### T4 — Answer relevance

**Verifies**: answer addresses the question.

**Files**:
- `tests/test_answer_relevance.py`
- Embedding-cosine vs gold answer + LLM-judge fallback.

**Snippet**:
```python
def test_answer_relevance_cosine_mean():
    qs = load_jsonl("data/eval/base50.jsonl")
    cos = [cosine(embed(run_mode("tutor", q.text).text), embed(q.gold_answer)) for q in qs]
    assert mean(cos) >= 0.75
```

**Cadence**: nightly. **Gate**: cosine ≥0.75; judge ≥0.9.

**Source**: P10.

---

### T5 — Prompt regression

**Verifies**: prompt edits do not degrade metrics > 5% vs last-green report.

**Files**:
- `src/services/eval/runner.py` writes `reports/<date>_<mode>_<set>.json`.
- `tests/test_prompt_regression.py` diffs current vs `baselines.json`.

**Snippet**:
```python
def test_no_prompt_regression():
    last = json.load(open("data/eval/baselines.json"))
    curr = run_eval_set("base50", mode="tutor", prompt_version="v2")
    for metric in ("faithfulness", "answer_relevance", "context_precision@10"):
        assert curr[metric] >= last["tutor"][metric] - 0.05, f"{metric} regressed"
```

Prompts versioned by filename: `prompts/tutor_v1.py`, `tutor_v2.py`; `ModeSpec.system_prompt` resolved by version.

**Cadence**: on every prompt-file change. **Gate**: no metric drops > 5%.

**Source**: C9.

---

### T6 — Citation coverage + schema validity

**Verifies**: every factual claim has citation; every response schema-valid; citations point to live chunks.

**Files**:
- `tests/test_citations.py`
- `tests/test_schema_valid.py`

**Snippet**:
```python
def test_every_response_has_citation():
    for mode in ALL_MODES:
        out = run_mode(mode, "test query")
        assert mode_spec(mode).output_schema.model_validate(out) is not None  # NFR11
        assert len(out.citations) >= 1
        for c in out.citations:
            assert qdrant_has_point(c.chunk_id)
```

**Cadence**: every PR. **Gate**: 100% schema-valid (post 1-retry); 100% have ≥1 valid citation.

**Source**: A3, A5.

---

### T7 — Latency / cost

**Verifies**: p50/p95/p99 per mode; $/query distribution.

**Files**:
- `src/services/eval/perf.py` — N=20 per mode; reads `cost_log.jsonl` for $.
- `tests/test_perf_gate.py` — gate p95 thresholds.

**Snippet**:
```python
def test_p95_under_threshold():
    rep = json.load(open("data/eval/perf_latest.json"))
    for mode in ["tutor","quiz","navigate"]: assert rep[mode]["p95_ms"] <= 8000   # NFR1
    for mode in ["prereqs","research","path"]: assert rep[mode]["p95_ms"] <= 25000  # NFR2
```

**Cadence**: weekly + before release. **Gate**: NFR1 + NFR2 met; cost-per-query report archived.

**Source**: B6.

---

### T8 — Multi-agent QC

**Verifies**: supervisor `qc` node triggers retry when groundedness < τ; iter cap enforced.

**Files**:
- `tests/test_agents_qc.py`

**Snippet**:
```python
async def test_qc_retry_then_partial():
    state = AgentState(...)
    state.retrieval_results = [unrelated_chunk]   # forces qc fail
    out = await prereqs_graph.run(state)
    assert "iter cap hit" not in (out.errors or []) or out.qc_status == "fail"
    assert out.iter <= 12   # max_graph_iters for mode 6
```

**Cadence**: every PR touching `chat/agents/`. **Gate**: cap respected; partial+error emitted on overflow.

**Source**: B8.

---

### T9 — Vision gate

**Verifies**: vision only called per τ matrix; cost logged.

**Files**:
- `tests/test_vision_gate.py`

**Snippet**:
```python
@pytest.mark.parametrize("score,expect_vision", [(0.70, False), (0.55, True), (0.40, None)])
def test_vision_gate_matrix(score, expect_vision):
    f = Figure(ref="f1", caption="cap", score=score, ...)
    out = vision_gate([f], query="q")
    if expect_vision is None: assert out == []                       # dropped
    else: assert out[0].vision_used is expect_vision
def test_cost_log_row_per_vision_call(tmp_path, monkeypatch):
    monkeypatch.setattr("chat.cost.LOG_PATH", tmp_path / "vlog.jsonl")
    _ = vision_gate([fig_low_score], query="q")
    rows = read_jsonl(tmp_path / "vlog.jsonl")
    assert len(rows) == 1 and rows[0]["vision_used"] is True
```

**Cadence**: every PR touching `vision.py` or modes 3/9. **Gate**: matrix passes; cost row asserted.

**Source**: B4 strategy 2.

---

### T10 — Memory regression

**Verifies**: tutor remembers prior turn; auto-escalation works; cleanup on conv delete (NFR12).

**Files**:
- `tests/test_memory.py`

**Snippet**:
```python
def test_sliding_then_summary_then_vec(client):
    conv = create_conv("tutor")
    for i in range(35):
        client.post("/api/chat", json={"conv_id": conv.id, "query": f"turn {i}"})
    assert qdrant_has_collection(f"conv_{conv.id}")              # vec engaged
    client.delete(f"/api/conversations/{conv.id}")
    assert not qdrant_has_collection(f"conv_{conv.id}")          # NFR12
```

**Cadence**: every PR touching `memory.py`. **Gate**: all 3 strategies exercise; cleanup verified.

**Source**: C8, B2.

---

### T11 — Synthetic Q/A generation

**Verifies**: offline gen produces valid `base50.jsonl`.

**Files**:
- `tests/test_eval_generator.py`

**Snippet**:
```python
def test_generator_round_trip():
    qa = generate_qa(sections=3, n=5)
    assert len(qa) == 5
    for q in qa:
        assert q.gold_chunk_id and qdrant_has_point(q.gold_chunk_id)
        assert len(q.gold_answer) > 30
```

Bootstrap: `python -m src.services.eval.generator --n 50 --out data/eval/base50.jsonl`.

**Cadence**: on collection updates (regen `base50`); CI runs schema check.

**Source**: P10, B5.

---

## 4. Milestone ↔ test gate matrix

| Milestone | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | T9 | T10 | T11 | Extra gate |
|-----------|----|----|----|----|----|----|----|----|----|-----|-----|-----------|
| M1 Reranker | ✓ |✓ (lift ≥10%) | | | | | | | | | | NFR10 mem ≤2GB |
| M2 Modes+Schemas | ✓ | | | | | ✓ | | | | | | schema-repair path exercised |
| M3 Query upgrades | ✓ | ✓ (HyDE win on `navigator15`) | | | ✓ | | | | | | | |
| M4 Eval harness | | ✓ | ✓ | ✓ | | | | | | | ✓ | baselines committed |
| M5 Prereqs | ✓ | | | | | ✓ | | ✓ | | | | DAG cycle-break works |
| M6 Research | | | | | | ✓ | | ✓ | | | | stance F1 ≥0.6 on `stance20` |
| M7 Study path | ✓ | | | | | ✓ | ✓ | ✓ | | | | persist + replan verified |
| M8 Vision | | | | | | | | | ✓ | | | precision ≥0.7 on `vision20` |
| M9 Memory | ✓ | | | | | | | | | ✓ | | NFR12 cleanup |
| M10 Frontend | ✓ | | | | | | | | | | | tsc clean + browser smoke |

**Wave-exit gates**:
- Wave 1: T1 + T6 green; NFR8 (61 baseline tests) green.
- Wave 2: T2 + T3 + T4 + T11 green; `baselines.json` committed.
- Wave 3: T3 + T6 + T8 + T9 green; agent F1 + vision precision pass.
- Wave 4: T1 across all 11 modes + browser smoke; T5 regression clean.

---

## 5. CI sketch (post-M4)

```yaml
on PR:
  - .venv/bin/pytest src/services/chat/tests/ -v          # T1, T6, T8, T9, T10 fast set
  - python -m src.services.eval.runner --set base50 --mode <changed_modes>
  - diff_vs_baselines.py                                  # T5: fail if any metric drops >5%
nightly:
  - full base50 across all 11 modes
  - perf run (T7)
  - upload to data/eval/reports/
  - publish daily summary to docs/upgrades/Chat/eval_history.md
```

Local-only CI for now; promote to GitHub Actions when repo pushed.

---

## 6. Hand-labeled gates (one-time human work)

| File | Size | Purpose | Blocks |
|------|------|---------|--------|
| `data/eval/stance20.jsonl` | 20 | M6 stance F1 gate | M6 acceptance |
| `data/eval/vision20.jsonl` | 20 | M8 vision precision gate + τ calibration | M8 acceptance |
| `data/eval/navigator15.jsonl` | 15 | M3 HyDE lift gate | M3 acceptance |
| `data/eval/quiz10.jsonl` | 10 | M2 sanity on self-check | optional |

Author: project owner (`iohanlucasf19@gmail.com`). Effort: ~2h total.

---

## 7. Risk-driven extra tests

Mapping back to `implementation_plan.md §5` risks:

| Risk | Extra test |
|------|-----------|
| R1 Reranker lift < projected | T2 lift assert at M1 exit |
| R2 Stance F1 < 0.6 | T6 + hand-labeled `stance20` |
| R3 Iter cap in production | T8 cap assertion |
| R4 Schema-repair retry doubles cost | T7 cost-log + retry-rate metric |
| R5 KG stale | M-future: `tests/test_kg_freshness.py` (post-v1) |
| R6 Vision cost balloons | T9 cost-row assertion + per-day cap |
| R8 Reranker mem > 2GB | T1 RSS assertion at M1 |
| R9 Synth Q/A bias | hand-labeled subsets (stance20/vision20/navigator15) |
| R10 Per-conv collection sprawl | T10 cleanup + post-v1 TTL job |

---

## 8. Out of scope

- E2E browser tests (manual smoke for v1).
- Load tests (locust/k6).
- Chaos / fault injection.
- Mutation testing.
- Security scans (separate skill).

(Add later under `docs/upgrades/Chat/post_v1_test_plan.md` if scope grows.)
