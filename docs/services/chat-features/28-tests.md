# 28 — Tests inventory

## Totals

- Chat service: **212 tests** in `src/services/chat/tests/`
- Eval service: **14 tests** in `src/services/eval/tests/`
- All mocked (no real OpenAI, Qdrant, or DeepSeek calls)
- pytest 8.3.3 + pytest-asyncio 0.24.0

## Per-file breakdown

| File | Tests | Coverage |
|---|---|---|
| `test_books.py` | 8 | BookRegistry, collections_for_books, get_book |
| `test_retrieval.py` | 22 | hybrid_search shape, multi_query dedup, highlights |
| `test_reranker.py` | 3 | monotonic reorder, top_n cap, empty hits |
| `test_llm_router.py` | 9 | OpenAI/DeepSeek routing, list_providers, model registry |
| `test_store.py` | 13 | conversations CRUD, messages cascade, prefs |
| `test_sse.py` | 14 | SSE event ordering, error path, FastAPI endpoints |
| `test_modes.py` | 29 | 11 modes registered, schema validation, repair |
| `test_query_expansion.py` | 14 | HyDE, multi_query, decompose, dedup |
| `test_memory.py` | 27 | strategies, auto-escalation, cleanup |
| `test_agents_graph.py` | 9 | StateGraph runner, iter cap, retry |
| `test_agents_prereqs.py` | 15 | cycle detection, topo sort, run_prereqs |
| `test_agents_research.py` | 9 | claim extraction, stance, F1 ≥ 0.6 (0.762 actual) |
| `test_vision_gate.py` | 15 | thresholds, budget, precision ≥ 0.7 (1.00 actual) |
| `test_agents_study_path.py` | 14 | decompose, bucketing, persist, replan |
| **Eval** | | |
| `eval/tests/test_eval.py` | 14 | dataset roundtrip, context_precision/recall edge cases |

## Run

```bash
# All chat + eval tests
.venv/bin/python -m pytest src/services/chat/tests/ src/services/eval/tests/ -q

# Single file with verbose output
.venv/bin/python -m pytest src/services/chat/tests/test_reranker.py -v

# Stop on first failure
.venv/bin/python -m pytest src/services/chat/tests/ -x
```

## Mocking patterns

### LLM (OpenAI)

```python
from unittest.mock import AsyncMock, patch

with patch("src.services.chat.query_expansion._llm_short",
           new=AsyncMock(return_value='{"goals":["g1","g2"]}')):
    out = await decompose_goal(state)
```

### Qdrant

```python
def test_x(monkeypatch):
    fake_points = [SimpleNamespace(id="a", score=0.9, payload={...})]
    fake_client = MagicMock()
    fake_client.query_points.return_value.points = fake_points
    monkeypatch.setattr("src.core.qdrant_store.client", lambda: fake_client)
```

### Reranker (cached_property)

```python
def test_reranker(monkeypatch):
    r = CrossEncoderReranker()
    class FakeModel:
        def predict(self, pairs, show_progress_bar=False): return [0.9, 0.1]
    r.__dict__["_model"] = FakeModel()   # bypass cached_property
    out = r.rerank("q", [src1, src2], top_n=2)
```

### SQLite store

```python
def test_store(tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.chat.store.DB_PATH", tmp_path / "test.db")
    init_db()
    # ... use the in-tmp database
```

### FastAPI TestClient

```python
from fastapi.testclient import TestClient
from src.services.chat.api import app

def test_health():
    c = TestClient(app)
    assert c.get("/api/health").json() == {"status": "ok"}
```

## Gate metrics

| Gate | Threshold | Achieved | Source |
|---|---|---|---|
| Stance F1 (M6) | ≥ 0.6 | 0.762 | `test_agents_research.py::test_stance_f1_on_labeled_set` |
| Vision precision (M8) | ≥ 0.7 | 1.00 | `test_vision_gate.py::test_precision_on_vision20` |
| Wall (all milestones) | 0 violations | 0 | grep |
| Backward compat | original 61 tests green | 226/226 green | `pytest -q` |

## CI

Not wired yet. Plan: add GitHub Actions on PR — `pytest` + `tsc --noEmit` + wall grep.
