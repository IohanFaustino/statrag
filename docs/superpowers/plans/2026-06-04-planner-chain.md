# Chained Question-Decomposition Query Planner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-call query planner with a flag-gated 3-step prompt chain (decompose → expand → consolidate) that does explicit question decomposition, then add an offline 3-model comparison eval.

**Architecture:** `extract_concepts_ex` becomes a dispatcher: `TUTOR_PLANNER_CHAIN=1` routes to `extract_concepts_chain` (3 nano calls), with the existing single-call planner (refactored to `_extract_concepts_single`) as default + automatic fallback on any chain exception. Output stays `QueryPlan`, so downstream is untouched. A new eval module mirrors `ts_components_compare.py`.

**Tech Stack:** Python 3.12, existing deep-tutor infra (`_async_client`/`aclient_for`, `strip_fences`, `QueryPlan`), pydantic, pytest; TypeScript/Vitest for the modal node.

**Spec:** `docs/superpowers/specs/2026-06-04-planner-chain-design.md`

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/services/chat/prompts/deep_tutor.py` | +3 prompts: `PLANNER_DECOMPOSE_PROMPT`, `PLANNER_EXPAND_PROMPT`, `PLANNER_CONSOLIDATE_PROMPT` |
| `src/services/chat/agents/deep_tutor.py` | chain step fns + parsers + `extract_concepts_chain` + dispatcher refactor + `_PLANNER_CHAIN_ON` |
| `src/services/chat/tests/test_planner_chain.py` | unit tests: parsers, chain assembler, dispatcher routing/fallback |
| `src/services/chat/eval/planner_chain_compare.py` | offline 3-model + baseline eval |
| `src/services/chat/tests/test_planner_chain_eval.py` | CI unit tests for eval pure helpers |
| `web/src/data/tutorPipeline.ts` | planner node desc → "decompose → expand → consolidate" |
| `docs/services/chat-features/54-planner-chain.md` | new per-feature doc |
| `docs/services/chat-features/36-deep-tutor.md` | env table += `TUTOR_PLANNER_CHAIN` |
| `docs/services/chat-features/45-query-planner-coverage.md` | flow note for the chain |
| `docs/system/invariants.md`, `docs/system/changelog.md` | invariant + changelog entry |
| `docs/superpowers/eval/2026-06-04-planner-chain-model-compare.md` | the eval artifact (Task 8) |

`QueryPlan` (existing, `deep_tutor.py`): `NamedTuple(concepts: list[str], suggested_authors: int, queries: list[str], facets: list[str])`. The consolidate JSON key is `perspectives` (mapped to `suggested_authors`), matching today's single-call planner.

---

## Task 1: Three chain prompts

**Files:**
- Modify: `src/services/chat/prompts/deep_tutor.py` (append 3 prompts)
- Test: `src/services/chat/tests/test_planner_chain.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_planner_chain.py
"""Unit tests for the chained question-decomposition query planner."""
from src.services.chat.prompts import deep_tutor as P


def test_chain_prompts_exist_and_mention_keys():
    assert "sub_questions" in P.PLANNER_DECOMPOSE_PROMPT
    # decompose must keep the application + related-framings guarantees
    assert "application" in P.PLANNER_DECOMPOSE_PROMPT.lower()
    assert "related" in P.PLANNER_DECOMPOSE_PROMPT.lower()
    assert "items" in P.PLANNER_EXPAND_PROMPT
    for k in ("concept", "query", "facet"):
        assert k in P.PLANNER_EXPAND_PROMPT
    for k in ("concepts", "perspectives", "facets", "queries"):
        assert k in P.PLANNER_CONSOLIDATE_PROMPT
    assert "{max_authors}" in P.PLANNER_CONSOLIDATE_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_planner_chain.py::test_chain_prompts_exist_and_mention_keys -v`
Expected: FAIL — `AttributeError` (prompts not defined).

- [ ] **Step 3: Write minimal implementation**

Append to `src/services/chat/prompts/deep_tutor.py`:

```python
PLANNER_DECOMPOSE_PROMPT: str = """\
<role>
You are step 1 (DECOMPOSE) of the query planner for a statistics / machine-learning
/ econometrics tutor. You break the user question into the atomic sub-questions the
answer must resolve.
</role>

<task>
Return a JSON object: {"sub_questions": [...]}.
- 2-5 short, self-contained sub-questions. Each names ONE thing the answer must
  cover (a definition, a formula, a component, a comparison axis). Atomic: no
  sub-question should bundle two distinct ideas.
- ALWAYS include one APPLICATION-CASE sub-question — a real, applied or empirical
  use of the concept (e.g. "What is a worked empirical example of the bias-variance
  tradeoff?").
- ALWAYS include one RELATED-FRAMINGS sub-question — the other contexts or parent
  theories the concept belongs to beyond the obvious one (e.g. "In what other
  settings does the bias-variance tradeoff arise, such as regularization or model
  selection?").
- Narrow/factual questions yield 2; broad/comparative yield up to 5.
</task>

<rules>
Output ONLY the JSON object. Ground every sub-question in the user question; invent
nothing unrelated. English only.
</rules>

<examples>
Q: "State the bias of an unbiased estimator." ->
  {"sub_questions": ["What is the definition and formula for the bias of an estimator?",
    "What condition makes an estimator unbiased?",
    "What is a real case where estimator bias matters in practice?",
    "In what other settings does estimator bias arise (e.g. regularization, shrinkage)?"]}
Q: "What is the bias-variance tradeoff?" ->
  {"sub_questions": ["What is the definition and formula for bias?",
    "What is the definition and formula for variance?",
    "How does the mean squared error decompose into bias, variance, and irreducible error?",
    "What is a worked empirical example of the bias-variance tradeoff?",
    "In what other settings does the bias-variance tradeoff arise (e.g. regularization, model selection, ensembles)?"]}
</examples>
"""


PLANNER_EXPAND_PROMPT: str = """\
<role>
You are step 2 (EXPAND) of the query planner. You turn each sub-question into a
retrieval-ready item.
</role>

<task>
Input (next message): the original question and a numbered list of sub-questions.
Return a JSON object: {"items": [...]}, ONE item per sub-question, IN ORDER. Each item:
- "sub_question": the sub-question text, copied verbatim.
- "concept": the canonical textbook term it targets (single word or short noun
  phrase, max 4 words; no verbs/adjectives/generic words).
- "query": a self-contained retrieval query that would surface this from a textbook
  (e.g. "formula for the variance of an estimator"). NEVER just echo the question.
- "facet": the specific thing the ANSWER must cover for this sub-question (e.g.
  "variance definition + formula").
</task>

<rules>
Output ONLY the JSON object. Exactly one item per input sub-question, same order.
English only. Ground everything in the inputs.
</rules>
"""


PLANNER_CONSOLIDATE_PROMPT: str = """\
<role>
You are step 3 (CONSOLIDATE) of the query planner. You compress the expanded items
into the final retrieval plan and judge how many author perspectives the answer
warrants.
</role>

<task>
Input (next message): the original question and the expanded items (each with
concept, query, facet). Return a JSON object with these keys:
- "concepts": 1-3 canonical concept strings (dedupe near-duplicates; keep the most
  central).
- "perspectives": integer 1-{max_authors} = how many DISTINCT author perspectives
  the answer benefits from, judged from the question's breadth (1 = narrow/factual;
  2 = standard; 3+ = broad/debated/comparative). Be generous (4-5) only when several
  distinct treatments genuinely add value.
- "facets": up to 6 facets the answer must cover — the deduped union of the items'
  facets. Merge near-duplicates into one.
- "queries": up to 5 self-contained retrieval queries — the deduped union of the
  items' queries (one per surviving facet). Do NOT just repeat the question.
</task>

<rules>
Output ONLY the JSON object. Preserve the application-case and related-framings
facets/queries — do not drop them in dedupe. English only.
</rules>
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_planner_chain.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/prompts/deep_tutor.py src/services/chat/tests/test_planner_chain.py
git commit -m "feat(planner): add decompose/expand/consolidate chain prompts"
```

---

## Task 2: Chain parsers + step functions + assembler

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py` (import the 3 prompts; add parsers, step fns, `extract_concepts_chain`)
- Test: `src/services/chat/tests/test_planner_chain.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
import pytest
from src.services.chat.agents import deep_tutor as DT


def test_parse_decompose_clamps_and_strips():
    raw = '```json\n{"sub_questions":["a"," b ","","c","d","e","f"]}\n```'
    assert DT._parse_decompose(raw) == ["a", "b", "c", "d", "e"]  # max 5, stripped, no empties


def test_parse_decompose_empty_raises():
    with pytest.raises(ValueError):
        DT._parse_decompose('{"sub_questions": []}')


def test_parse_expand_items():
    raw = '{"items":[{"sub_question":"q1","concept":"bias","query":"bias formula","facet":"bias def"}]}'
    items = DT._parse_expand(raw)
    assert items == [{"sub_question": "q1", "concept": "bias", "query": "bias formula", "facet": "bias def"}]


def test_parse_expand_empty_raises():
    with pytest.raises(ValueError):
        DT._parse_expand('{"items": []}')


def test_parse_consolidate_builds_queryplan_and_clamps():
    raw = ('{"concepts":["a","b","c","d"],"perspectives":9,'
           '"facets":["f1","f2","f3","f4","f5","f6","f7"],'
           '"queries":["q1","q2","q3","q4","q5","q6"]}')
    plan = DT._parse_consolidate(raw, max_authors=4)
    assert plan.concepts == ["a", "b", "c"]              # ≤3
    assert plan.suggested_authors == 4                   # clamped to max_authors
    assert plan.facets == ["f1", "f2", "f3", "f4", "f5", "f6"]  # ≤6
    assert plan.queries == ["q1", "q2", "q3", "q4", "q5"]       # ≤5


def test_parse_consolidate_no_queries_raises():
    with pytest.raises(ValueError):
        DT._parse_consolidate('{"concepts":["a"],"perspectives":1,"facets":["f"],"queries":[]}', max_authors=4)


def test_extract_concepts_chain_composes_steps(monkeypatch):
    async def fake_decompose(q, *, model):
        return ["sq1", "sq2"]

    async def fake_expand(q, subqs, *, model):
        assert subqs == ["sq1", "sq2"]
        return [{"sub_question": "sq1", "concept": "c", "query": "qq", "facet": "ff"}]

    async def fake_consolidate(items, *, model, max_authors):
        assert items and items[0]["concept"] == "c"
        return DT.QueryPlan(["c"], 2, ["qq"], ["ff"])

    monkeypatch.setattr(DT, "_planner_decompose", fake_decompose)
    monkeypatch.setattr(DT, "_planner_expand", fake_expand)
    monkeypatch.setattr(DT, "_planner_consolidate", fake_consolidate)
    plan = asyncio.run(DT.extract_concepts_chain("the question", model=None, max_authors=4))
    assert plan == DT.QueryPlan(["c"], 2, ["qq"], ["ff"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_planner_chain.py -v`
Expected: FAIL — `AttributeError` (parsers/step fns/`extract_concepts_chain` not defined).

- [ ] **Step 3: Write minimal implementation**

In `src/services/chat/agents/deep_tutor.py`, add the 3 prompt names to the existing import block (`from src.services.chat.prompts.deep_tutor import ( ... )`, around line 50):

```python
    PLANNER_DECOMPOSE_PROMPT,
    PLANNER_EXPAND_PROMPT,
    PLANNER_CONSOLIDATE_PROMPT,
```

Then add the parsers, step fns, and assembler immediately AFTER `extract_concepts_ex` (after its `def` block, around line 1102):

```python
# ---------------------------------------------------------------------------
# Chained question-decomposition planner (flag-gated; see TUTOR_PLANNER_CHAIN).
# decompose -> expand -> consolidate, three nano calls. Output is a QueryPlan,
# identical to the single-call planner. Any step failure raises and the
# dispatcher (extract_concepts_ex) degrades to the single-call planner.
# ---------------------------------------------------------------------------


def _parse_decompose(raw: str) -> list[str]:
    data = json.loads(strip_fences(raw or "{}"))
    subs = [str(x).strip() for x in (data.get("sub_questions") or []) if str(x).strip()][:5]
    if not subs:
        raise ValueError("decompose produced no sub_questions")
    return subs


def _parse_expand(raw: str) -> list[dict]:
    data = json.loads(strip_fences(raw or "{}"))
    items = []
    for it in (data.get("items") or []):
        q = str(it.get("query", "")).strip()
        f = str(it.get("facet", "")).strip()
        if not q or not f:
            continue
        items.append({
            "sub_question": str(it.get("sub_question", "")).strip(),
            "concept": str(it.get("concept", "")).strip(),
            "query": q,
            "facet": f,
        })
    if not items:
        raise ValueError("expand produced no usable items")
    return items


def _parse_consolidate(raw: str, max_authors: int) -> "QueryPlan":
    data = json.loads(strip_fences(raw or "{}"))
    concepts = [str(x).strip() for x in (data.get("concepts") or []) if str(x).strip()][:3]
    n = int(data.get("perspectives", min(2, max_authors)))
    n = max(1, min(max_authors, n))
    facets = [str(x).strip() for x in (data.get("facets") or []) if str(x).strip()][:6]
    queries = [str(x).strip() for x in (data.get("queries") or []) if str(x).strip()][:5]
    if not queries or not facets:
        raise ValueError("consolidate produced no queries/facets")
    return QueryPlan(concepts, n, queries, facets)


async def _planner_call(messages: list[dict], *, model: str) -> str:
    oa = _async_client(model)
    resp = await oa.chat.completions.create(
        model=model, messages=messages, temperature=0.0, max_completion_tokens=300,
    )
    return resp.choices[0].message.content or "{}"


async def _planner_decompose(query: str, *, model: str) -> list[str]:
    raw = await _planner_call(
        [{"role": "system", "content": PLANNER_DECOMPOSE_PROMPT},
         {"role": "user", "content": query}], model=model)
    return _parse_decompose(raw)


async def _planner_expand(query: str, subqs: list[str], *, model: str) -> list[dict]:
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(subqs, 1))
    user = f"original question: {query}\n\nsub-questions:\n{numbered}"
    raw = await _planner_call(
        [{"role": "system", "content": PLANNER_EXPAND_PROMPT},
         {"role": "user", "content": user}], model=model)
    return _parse_expand(raw)


async def _planner_consolidate(items: list[dict], *, model: str, max_authors: int) -> "QueryPlan":
    lines = [f"- sub_question: {it['sub_question']}\n  concept: {it['concept']}\n"
             f"  query: {it['query']}\n  facet: {it['facet']}" for it in items]
    user = "expanded items:\n" + "\n".join(lines)
    raw = await _planner_call(
        [{"role": "system",
          "content": PLANNER_CONSOLIDATE_PROMPT.format(max_authors=max_authors)},
         {"role": "user", "content": user}], model=model)
    return _parse_consolidate(raw, max_authors)


async def extract_concepts_chain(
    query: str, *, model: str | None = None, max_authors: int = 4
) -> "QueryPlan":
    """3-step chained planner: decompose -> expand -> consolidate. Raises on any
    step failure so the dispatcher can degrade to the single-call planner."""
    max_authors = max(1, int(max_authors))
    chosen = model or settings.openai_model_nano
    subqs = await _planner_decompose(query, model=chosen)
    items = await _planner_expand(query, subqs, model=chosen)
    return await _planner_consolidate(items, model=chosen, max_authors=max_authors)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_planner_chain.py -v`
Expected: PASS (7 tests added; 8 total in file).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_planner_chain.py
git commit -m "feat(planner): 3-step chain parsers, step fns, extract_concepts_chain"
```

---

## Task 3: Dispatcher + flag (refactor single-call to `_extract_concepts_single`)

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py` (`extract_concepts_ex` → dispatcher; add `_PLANNER_CHAIN_ON`)
- Test: `src/services/chat/tests/test_planner_chain.py`

- [ ] **Step 1: Write the failing test**

```python
def test_dispatcher_flag_off_uses_single(monkeypatch):
    async def fake_single(q, *, model, max_authors):
        return DT.QueryPlan(["single"], 1, ["sq"], ["sf"])

    async def boom_chain(q, *, model, max_authors):
        raise AssertionError("chain must NOT run when flag off")

    monkeypatch.setattr(DT, "_PLANNER_CHAIN_ON", False)
    monkeypatch.setattr(DT, "_extract_concepts_single", fake_single)
    monkeypatch.setattr(DT, "extract_concepts_chain", boom_chain)
    plan = asyncio.run(DT.extract_concepts_ex("q", model=None, max_authors=4))
    assert plan.concepts == ["single"]


def test_dispatcher_flag_on_uses_chain(monkeypatch):
    async def fake_single(q, *, model, max_authors):
        return DT.QueryPlan(["single"], 1, ["sq"], ["sf"])

    async def fake_chain(q, *, model, max_authors):
        return DT.QueryPlan(["chain"], 2, ["cq"], ["cf"])

    monkeypatch.setattr(DT, "_PLANNER_CHAIN_ON", True)
    monkeypatch.setattr(DT, "_extract_concepts_single", fake_single)
    monkeypatch.setattr(DT, "extract_concepts_chain", fake_chain)
    plan = asyncio.run(DT.extract_concepts_ex("q", model=None, max_authors=4))
    assert plan.concepts == ["chain"]


def test_dispatcher_chain_failure_falls_back_to_single(monkeypatch):
    async def fake_single(q, *, model, max_authors):
        return DT.QueryPlan(["single"], 1, ["sq"], ["sf"])

    async def fail_chain(q, *, model, max_authors):
        raise RuntimeError("chain blew up")

    monkeypatch.setattr(DT, "_PLANNER_CHAIN_ON", True)
    monkeypatch.setattr(DT, "_extract_concepts_single", fake_single)
    monkeypatch.setattr(DT, "extract_concepts_chain", fail_chain)
    plan = asyncio.run(DT.extract_concepts_ex("q", model=None, max_authors=4))
    assert plan.concepts == ["single"]


def test_dispatcher_empty_query_short_circuits():
    plan = asyncio.run(DT.extract_concepts_ex("   ", model=None, max_authors=4))
    assert plan == DT.QueryPlan([], 1, [], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_planner_chain.py -k dispatcher -v`
Expected: FAIL — `_PLANNER_CHAIN_ON` / `_extract_concepts_single` not defined.

- [ ] **Step 3: Write minimal implementation**

In `deep_tutor.py`, **rename** the existing `async def extract_concepts_ex(...)` body to `async def _extract_concepts_single(...)`, removing only its top guards (the `max_authors = max(1, ...)` line and the `if not query.strip(): return QueryPlan([], 1, [], [])` line move to the new dispatcher). Keep the rest of the body (the single API call + parse + except fallback to `extract_concepts`) verbatim. Its signature:

```python
async def _extract_concepts_single(
    query: str, *, model: str | None = None, max_authors: int = 4
) -> "QueryPlan":
    """Single-call planner (legacy). One nano call -> QueryPlan; degrades to the
    keyword heuristic on failure."""
    chosen_model = model or settings.openai_model_nano
    oa = _async_client(chosen_model)
    try:
        resp = await oa.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system",
                 "content": EXTRACT_CONCEPTS_BUDGET_PROMPT.format(max_authors=max_authors)},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
            max_completion_tokens=400,
        )
        raw = strip_fences(resp.choices[0].message.content or "{}")
        parsed = json.loads(raw)
        concepts = [str(x).strip() for x in (parsed.get("concepts") or []) if str(x).strip()][:3]
        n = int(parsed.get("perspectives", min(2, max_authors)))
        n = max(1, min(max_authors, n))
        queries = [str(x).strip() for x in (parsed.get("queries") or []) if str(x).strip()][:4]
        facets = [str(x).strip() for x in (parsed.get("facets") or []) if str(x).strip()][:6]
        return QueryPlan(concepts, n, queries, facets)
    except Exception:  # noqa: BLE001
        logger.exception("single-call planner failed; degrading to keyword heuristic + neutral budget")
        concepts = await extract_concepts(query, model=model)
        return QueryPlan(concepts, min(2, max_authors), [], [])
```

Add the flag near the other module-level `os.environ.get(...)` planner flags (e.g. just above `extract_concepts_ex`):

```python
# Flag-gated chained planner (decompose->expand->consolidate). Default OFF.
_PLANNER_CHAIN_ON = os.environ.get("TUTOR_PLANNER_CHAIN", "0") == "1"
```

Add the new thin dispatcher (this REPLACES the old `extract_concepts_ex` name):

```python
async def extract_concepts_ex(
    query: str, *, model: str | None = None, max_authors: int = 4
) -> "QueryPlan":
    """Query planner dispatcher. With TUTOR_PLANNER_CHAIN=1 runs the 3-step chain
    (decompose->expand->consolidate); otherwise (or on any chain failure) runs the
    single-call planner. Output is always a QueryPlan."""
    max_authors = max(1, int(max_authors))
    if not query.strip():
        return QueryPlan([], 1, [], [])
    if _PLANNER_CHAIN_ON:
        try:
            return await extract_concepts_chain(query, model=model, max_authors=max_authors)
        except Exception:  # noqa: BLE001
            logger.exception("planner chain failed; degrading to single-call planner")
    return await _extract_concepts_single(query, model=model, max_authors=max_authors)
```

Ordering note: `extract_concepts_chain` (Task 2) is defined after `extract_concepts_ex`; since the dispatcher references it at call time (not import time), forward reference is fine. Keep `_extract_concepts_single` defined before or after — both are module-level and resolved at call time.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_planner_chain.py -v`
Expected: PASS (12 tests in file).

- [ ] **Step 5: Run the existing planner/tutor suites (no regression)**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_query_planner_coverage.py src/services/chat/tests/test_deep_tutor.py -q`
Expected: all pass (single-call path unchanged when flag off).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_planner_chain.py
git commit -m "feat(planner): flag-gated dispatcher with single-call fallback"
```

---

## Task 4: Modal node + web test

**Files:**
- Modify: `web/src/data/tutorPipeline.ts` (planner node `desc`, id `expansion`, ~line 42)
- Test: `web/src/components/PipelineDiagram.test.tsx` (only if it asserts the old desc)

- [ ] **Step 1: Check whether a web test pins the planner desc**

Run: `grep -n "concepts, targeted retrieval queries" web/src/components/PipelineDiagram.test.tsx web/src/data/*.ts`
Expected: shows only the `tutorPipeline.ts` occurrence (if a test also matches, update it in Step 3).

- [ ] **Step 2: Update the node description**

In `web/src/data/tutorPipeline.ts`, change the `id: "expansion"` node `desc` from:

```ts
      desc: "Interprets the question → concepts, targeted retrieval queries, and the facets the answer must cover (folds into the nano call).",
```

to:

```ts
      desc: "Interprets the question. Default: one nano call → concepts, queries, facets. With TUTOR_PLANNER_CHAIN=1: a 3-step prompt chain — decompose (question → atomic sub-questions) → expand (per sub-question: concept, query, facet) → consolidate (dedupe, budget perspectives) → QueryPlan.",
```

- [ ] **Step 3: Run web tests**

Run: `cd web && npx vitest run src/components/PipelineDiagram.test.tsx`
Expected: PASS. If a test asserted the old desc substring, update that assertion to a stable substring still present (e.g. `"Interprets the question"`).

- [ ] **Step 4: Commit**

```bash
git add web/src/data/tutorPipeline.ts web/src/components/PipelineDiagram.test.tsx
git commit -m "feat(planner): modal node reflects decompose/expand/consolidate chain"
```

---

## Task 5: Docs lockstep (env table, flow, feature doc, invariants, changelog)

**Files:**
- Create: `docs/services/chat-features/54-planner-chain.md`
- Modify: `docs/services/chat-features/36-deep-tutor.md` (env table), `45-query-planner-coverage.md` (flow), `docs/system/invariants.md`, `docs/system/changelog.md`

- [ ] **Step 1: Add the env flag to the doc-36 env table**

In `docs/services/chat-features/36-deep-tutor.md`, find the `TUTOR_*` env table and add a row:

```
| `TUTOR_PLANNER_CHAIN` | `0` | When `1`, the query planner runs the 3-step decompose→expand→consolidate chain (3 nano calls) instead of the single call; falls back to single-call on any chain error. |
```

- [ ] **Step 2: Note the chain in doc-45 flow**

In `docs/services/chat-features/45-query-planner-coverage.md`, under `## Flow`, append after the planner line:

```
> **Chained variant (`TUTOR_PLANNER_CHAIN=1`):** the single `extract_concepts_ex`
> call is replaced by `extract_concepts_chain` — decompose (question → atomic
> sub-questions, incl. an application-case and a related-framings sub-question) →
> expand (one {concept, query, facet} per sub-question) → consolidate (dedupe +
> perspectives budget) → the same `QueryPlan`. Any step failure degrades to the
> single call. See doc 54.
```

- [ ] **Step 3: Create the per-feature doc**

Create `docs/services/chat-features/54-planner-chain.md`:

```markdown
# 54 — Chained question-decomposition query planner

## Why

The single-call planner (doc 45) crams concepts + perspectives + facets + queries
into one nano JSON reply. Splitting it into an explicit prompt chain makes the
question-decomposition step first-class and lets each stage be judged and swapped.

## Flow (TUTOR_PLANNER_CHAIN=1)

​```mermaid
flowchart LR
  Q[User question] --> D[1. DECOMPOSE\nsub_questions]
  D --> E[2. EXPAND\nconcept+query+facet per sub_q]
  E --> C[3. CONSOLIDATE\ndedupe + perspectives]
  C --> P[QueryPlan]
  D -. any step error .-> S[single-call planner]
  E -. .-> S
  C -. .-> S
  S --> P
​```

3 nano calls (`max_completion_tokens=300` each), plain JSON + `strip_fences` (no
`response_format` — keeps qwen working, see memory `qwen-plus-json-schema-hang`).
Default OFF; single-call planner is the default and the fallback.

## Artifacts

- Backend: `extract_concepts_chain`, `_planner_{decompose,expand,consolidate}`,
  `_parse_{decompose,expand,consolidate}`, dispatcher `extract_concepts_ex`,
  `_extract_concepts_single`, flag `_PLANNER_CHAIN_ON` — `agents/deep_tutor.py`.
- Prompts: `PLANNER_{DECOMPOSE,EXPAND,CONSOLIDATE}_PROMPT` — `prompts/deep_tutor.py`.
- Env: `TUTOR_PLANNER_CHAIN` (doc 36 env table).
- Modal: planner node desc — `web/src/data/tutorPipeline.ts`.
- Tests: `tests/test_planner_chain.py`.
- Eval: `eval/planner_chain_compare.py` → `docs/superpowers/eval/2026-06-04-planner-chain-model-compare.md`.
```

(Note: in the real file the mermaid fence is three backticks with no zero-width
characters — the `​` marks above are only to show fence placement in this plan.)

- [ ] **Step 4: Add an invariant + changelog entry**

In `docs/system/invariants.md`, add under the planner/retrieval section:

```
- The query planner always returns a `QueryPlan` and never raises to its caller.
  Whether single-call or chained (`TUTOR_PLANNER_CHAIN`), failure degrades:
  chain → single-call → keyword heuristic.
```

In `docs/system/changelog.md`, prepend a dated entry:

```
## 2026-06-04 — Chained question-decomposition query planner
Added flag-gated 3-step planner chain (decompose→expand→consolidate) behind
`TUTOR_PLANNER_CHAIN` (default off), single-call planner as fallback. New prompts,
doc 54, and a 3-model eval harness. Downstream QueryPlan unchanged.
```

- [ ] **Step 5: Commit**

```bash
git add docs/services/chat-features/54-planner-chain.md docs/services/chat-features/36-deep-tutor.md docs/services/chat-features/45-query-planner-coverage.md docs/system/invariants.md docs/system/changelog.md
git commit -m "docs(planner): doc 54, env table, flow, invariant, changelog for the chain"
```

---

## Task 6: Eval module + CI unit tests

**Files:**
- Create: `src/services/chat/eval/planner_chain_compare.py`
- Test: `src/services/chat/tests/test_planner_chain_eval.py`

Reuse the structure of `src/services/chat/eval/ts_components_compare.py` (constants, `_load`/`_write`, `_parse_judge`, `_render_artifact`, `main()` with `--step`). Differences: contestants run the planner (no Qdrant); judge dims are decomposition/coverage/targeting/redundancy; the "answer" judged is a rendered plan.

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_planner_chain_eval.py
"""CI unit tests for the planner-chain eval (pure helpers only)."""
from src.services.chat.eval import planner_chain_compare as pc


def test_constants():
    assert pc.MODELS == ["gpt-5.4-nano-2026-03-17", "gemini-2.5-flash", "qwen-plus"]
    assert pc.JUDGE_MODEL == "gpt-5.4-nano-2026-03-17"
    assert len(pc.QUESTIONS) == 3
    assert pc.JUDGE_DIMS == ("decomposition", "coverage", "targeting", "redundancy")
    assert pc.MAX_TOK == 300 and pc.TIMEOUT_S == 60


def test_render_plan_text():
    txt = pc._render_plan({"sub_questions": ["a", "b"], "concepts": ["c"],
                           "perspectives": 2, "facets": ["f"], "queries": ["q"]})
    for needle in ("a", "b", "c", "f", "q", "2"):
        assert needle in txt


def test_parse_judge_ok_and_fallback():
    good = '{"decomposition":4,"coverage":5,"targeting":3,"redundancy":4}'
    d = pc._parse_judge(good)
    assert d["overall"] == 4.0
    assert pc._parse_judge("junk")["overall"] == 0.0


def test_render_artifact_has_rows():
    results = {
        ("gpt-5.4-nano-2026-03-17", 0): {
            "label": "nano-chain", "plan_text": "PLAN A", "in_tok": 100, "out_tok": 50,
            "ms": 900, "ok": True, "err": "",
            "scores": {"decomposition": 5, "coverage": 5, "targeting": 4, "redundancy": 4, "overall": 4.5}},
    }
    md = pc._render_artifact(results)
    assert "| contestant | question |" in md
    assert "nano-chain" in md and "4.5" in md and "$" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_planner_chain_eval.py -v`
Expected: FAIL — module not defined.

- [ ] **Step 3: Write minimal implementation**

Create `src/services/chat/eval/planner_chain_compare.py`:

```python
"""Offline eval: compare the chained planner across nano/gemini/qwen-plus, plus the
single-call (nano) baseline, on 3 fixed questions. Judge the produced plan. No Qdrant.

Run:
  .venv/bin/python -m src.services.chat.eval.planner_chain_compare --step run
  .venv/bin/python -m src.services.chat.eval.planner_chain_compare --step judge
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from src.services.chat._fences import strip_fences

MODELS = ["gpt-5.4-nano-2026-03-17", "gemini-2.5-flash", "qwen-plus"]
JUDGE_MODEL = "gpt-5.4-nano-2026-03-17"
QUESTIONS = [
    "State the bias of an unbiased estimator.",                 # narrow
    "What are the components of a time series?",                # standard
    "Compare L1 and L2 regularization.",                        # broad
]
MAX_TOK = 300
TIMEOUT_S = 60
JUDGE_DIMS = ("decomposition", "coverage", "targeting", "redundancy")

_ROOT = Path(__file__).resolve().parents[4]
_WORK = _ROOT / "docs" / "superpowers" / "eval" / "_work_planner"
_RESULTS = _WORK / "results.json"
_ARTIFACT = _ROOT / "docs" / "superpowers" / "eval" / "2026-06-04-planner-chain-model-compare.md"

JUDGE_PROMPT = (
    "You score a query planner's output for a stats/ML tutor, 1-5 each (5=best):\n"
    "decomposition (are the sub-questions/facets atomic and complete for the "
    "question?), coverage (do facets include an application-case and a "
    "related-framings facet?), targeting (are queries self-contained and textbook-"
    "phrased, ~one per facet, NOT echoes of the question?), redundancy (5=no "
    "duplication, 1=heavy dup).\n"
    'Return ONLY JSON: {"decomposition":n,"coverage":n,"targeting":n,"redundancy":n}.'
)


def _render_plan(plan: dict) -> str:
    """Human-readable plan dump for judging + the artifact."""
    parts = []
    if plan.get("sub_questions"):
        parts.append("sub_questions:\n" + "\n".join(f"- {s}" for s in plan["sub_questions"]))
    parts.append(f"concepts: {plan.get('concepts')}")
    parts.append(f"perspectives: {plan.get('perspectives')}")
    parts.append("facets:\n" + "\n".join(f"- {f}" for f in (plan.get("facets") or [])))
    parts.append("queries:\n" + "\n".join(f"- {q}" for q in (plan.get("queries") or [])))
    return "\n".join(parts)


def _parse_judge(raw: str) -> dict:
    try:
        d = json.loads(strip_fences(raw))
        vals = {k: float(d.get(k, 0)) for k in JUDGE_DIMS}
    except Exception:
        vals = {k: 0.0 for k in JUDGE_DIMS}
    vals["overall"] = round(sum(vals.values()) / len(JUDGE_DIMS), 2)
    return vals


def _load_results() -> dict:
    if not _RESULTS.exists():
        return {}
    raw = json.loads(_RESULTS.read_text(encoding="utf-8"))
    return {(r["model"], r["qi"]): r for r in raw}


def _save_results(results: dict) -> None:
    _WORK.mkdir(parents=True, exist_ok=True)
    rows = []
    for (model, qi), r in results.items():
        rows.append({"model": model, "qi": qi, **{k: v for k, v in r.items()}})
    _RESULTS.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _render_artifact(results: dict) -> str:
    from src.services.chat.cost import usd_est

    lines = [
        "# Planner-chain model comparison — decompose→expand→consolidate", "",
        f"_contestants run the 3-step chain (baseline = single-call nano) · "
        f"judge={JUDGE_MODEL} · {len(QUESTIONS)} questions · plan-quality only_", "",
        "| contestant | question | overall | decomp | coverage | targeting | redundancy | out_tok | ms | USD |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (model, qi), r in sorted(results.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        sc = r.get("scores", {k: 0.0 for k in (*JUDGE_DIMS, "overall")})
        label = r.get("label", model)
        if not r.get("ok", False):
            lines.append(f"| {label} | Q{qi} | FAILED |  |  |  |  | {r.get('out_tok',0)} | {r.get('ms',0)} | _{r.get('err','')}_ |")
            continue
        usd = f"${usd_est(model, input_tokens=r['in_tok'], output_tokens=r['out_tok']):.4f}"
        lines.append(
            f"| {label} | Q{qi} | {sc['overall']} | {sc['decomposition']} | {sc['coverage']} | "
            f"{sc['targeting']} | {sc['redundancy']} | {r['out_tok']} | {r['ms']} | {usd} |")
    lines += ["", "## Questions", ""]
    for i, q in enumerate(QUESTIONS):
        lines.append(f"- Q{i}: {q}")
    lines += ["", "## Plan dumps", ""]
    for (model, qi), r in sorted(results.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        lines += [f"### {r.get('label', model)} — Q{qi}", "", "```", r.get("plan_text", "(none)"), "```", ""]
    lines += ["", "> Opus verdict appended after manual review.", ""]
    return "\n".join(lines)


async def _call_usage(model: str, messages: list[dict]) -> tuple[str, int, int]:
    """One capped+timed planner call; returns (content, in_tok, out_tok) from the
    response's real usage so the eval can compute true USD."""
    from src.services.chat.agents.deep_tutor import _async_client
    resp = await asyncio.wait_for(
        _async_client(model).chat.completions.create(
            model=model, messages=messages, temperature=0.0, max_completion_tokens=MAX_TOK),
        timeout=TIMEOUT_S)
    u = getattr(resp, "usage", None)
    return (resp.choices[0].message.content or "{}",
            int(getattr(u, "prompt_tokens", 0) or 0),
            int(getattr(u, "completion_tokens", 0) or 0))


async def step_run() -> None:
    """Produce plans for each (contestant × question), capturing real token usage.
    Persists incrementally. Calls DT's prompts + parsers directly (no Qdrant);
    production code is untouched."""
    from src.services.chat.agents import deep_tutor as DT

    results = _load_results()
    # chain contestants: run the 3 steps inline, summing usage across the 3 calls.
    for model in MODELS:
        for qi, q in enumerate(QUESTIONS):
            t0 = time.monotonic()
            itok = otok = 0
            try:
                raw, i1, o1 = await _call_usage(
                    model, [{"role": "system", "content": DT.PLANNER_DECOMPOSE_PROMPT},
                            {"role": "user", "content": q}])
                itok += i1; otok += o1
                subqs = DT._parse_decompose(raw)

                numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(subqs, 1))
                euser = f"original question: {q}\n\nsub-questions:\n{numbered}"
                raw, i2, o2 = await _call_usage(
                    model, [{"role": "system", "content": DT.PLANNER_EXPAND_PROMPT},
                            {"role": "user", "content": euser}])
                itok += i2; otok += o2
                items = DT._parse_expand(raw)

                clines = [f"- sub_question: {it['sub_question']}\n  concept: {it['concept']}\n"
                          f"  query: {it['query']}\n  facet: {it['facet']}" for it in items]
                cuser = "expanded items:\n" + "\n".join(clines)
                raw, i3, o3 = await _call_usage(
                    model, [{"role": "system",
                             "content": DT.PLANNER_CONSOLIDATE_PROMPT.format(max_authors=4)},
                            {"role": "user", "content": cuser}])
                itok += i3; otok += o3
                plan = DT._parse_consolidate(raw, 4)

                pd = {"sub_questions": subqs, "concepts": plan.concepts,
                      "perspectives": plan.suggested_authors, "facets": plan.facets, "queries": plan.queries}
                results[(model, qi)] = {"model": model, "qi": qi, "label": f"{_short(model)}-chain",
                                        "plan_text": _render_plan(pd), "in_tok": itok, "out_tok": otok,
                                        "ms": int((time.monotonic()-t0)*1000), "ok": True, "err": ""}
            except Exception as exc:  # noqa: BLE001
                results[(model, qi)] = {"model": model, "qi": qi, "label": f"{_short(model)}-chain",
                                        "plan_text": "", "in_tok": itok, "out_tok": otok,
                                        "ms": int((time.monotonic()-t0)*1000), "ok": False,
                                        "err": f"{type(exc).__name__}: {exc}"}
            _save_results(results)
            print(f"[{model} Q{qi}] {'ok' if results[(model,qi)]['ok'] else 'FAILED'} "
                  f"out_tok={results[(model,qi)]['out_tok']} {results[(model,qi)]['ms']}ms")

    # baseline: single-call nano (one call), real usage.
    bmodel = JUDGE_MODEL
    for qi, q in enumerate(QUESTIONS):
        t0 = time.monotonic()
        try:
            raw, it, ot = await _call_usage(
                bmodel, [{"role": "system",
                          "content": DT.EXTRACT_CONCEPTS_BUDGET_PROMPT.format(max_authors=4)},
                         {"role": "user", "content": q}])
            parsed = json.loads(strip_fences(raw))
            concepts = [str(x).strip() for x in (parsed.get("concepts") or []) if str(x).strip()][:3]
            n = max(1, min(4, int(parsed.get("perspectives", 2))))
            facets = [str(x).strip() for x in (parsed.get("facets") or []) if str(x).strip()][:6]
            queries = [str(x).strip() for x in (parsed.get("queries") or []) if str(x).strip()][:5]
            pd = {"concepts": concepts, "perspectives": n, "facets": facets, "queries": queries}
            results[("baseline", qi)] = {"model": bmodel, "qi": qi, "label": "single-call(nano) baseline",
                                         "plan_text": _render_plan(pd), "in_tok": it, "out_tok": ot,
                                         "ms": int((time.monotonic()-t0)*1000), "ok": True, "err": ""}
        except Exception as exc:  # noqa: BLE001
            results[("baseline", qi)] = {"model": bmodel, "qi": qi, "label": "single-call(nano) baseline",
                                         "plan_text": "", "in_tok": 0, "out_tok": 0,
                                         "ms": int((time.monotonic()-t0)*1000), "ok": False, "err": f"{type(exc).__name__}: {exc}"}
        _save_results(results)
        print(f"[baseline Q{qi}] {'ok' if results[('baseline',qi)]['ok'] else 'FAILED'}")


def _short(model: str) -> str:
    if model.startswith("gpt-5.4-nano"):
        return "nano"
    if model.startswith("gemini"):
        return "gemini"
    if model.startswith("qwen"):
        return "qwen"
    return model


async def step_judge() -> None:
    from src.services.chat.agents.deep_tutor import _async_client

    results = _load_results()
    assert results, "no results — run --step run first"

    async def judge_one(qi: int, plan_text: str) -> dict:
        user = f"QUESTION: {QUESTIONS[qi]}\n\nPLANNER OUTPUT:\n{plan_text}"
        try:
            resp = await asyncio.wait_for(_async_client(JUDGE_MODEL).chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": user}],
                temperature=0.0, max_completion_tokens=120), timeout=TIMEOUT_S)
            return _parse_judge(resp.choices[0].message.content or "")
        except Exception:
            return _parse_judge("")

    for key, r in results.items():
        r["scores"] = await judge_one(r["qi"], r.get("plan_text", "")) if r.get("ok") else _parse_judge("")
    _save_results(results)
    _ARTIFACT.write_text(_render_artifact(results), encoding="utf-8")
    print(f"wrote {_ARTIFACT}")


def main() -> None:
    ap = argparse.ArgumentParser(description="planner-chain model compare")
    ap.add_argument("--step", choices=["run", "judge"], required=True)
    args = ap.parse_args()
    asyncio.run(step_run() if args.step == "run" else step_judge())


if __name__ == "__main__":
    main()
```

Note: `_save_results`/`_load_results` round-trip the `scores` dict too (it is just
another key in each row), so judging persists.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_planner_chain_eval.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/eval/planner_chain_compare.py src/services/chat/tests/test_planner_chain_eval.py
git commit -m "eval(planner-chain): 3-model + baseline comparison harness"
```

---

## Task 7: Lint + full-suite gate

**Files:** none (verification only)

- [ ] **Step 1: Ruff**

Run: `.venv/bin/python -m ruff check src/services/chat/agents/deep_tutor.py src/services/chat/prompts/deep_tutor.py src/services/chat/eval/planner_chain_compare.py src/services/chat/tests/test_planner_chain.py src/services/chat/tests/test_planner_chain_eval.py`
Expected: clean (use `ruff` on PATH if `.venv/bin/ruff` missing). Fix inline.

- [ ] **Step 2: Full chat suite**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: all pass (existing + new planner tests).

- [ ] **Step 3: Web tests**

Run: `cd web && npx vitest run`
Expected: all pass.

- [ ] **Step 4: Commit (only if fixes needed)**

```bash
git add -A && git commit -m "chore(planner): lint + test gate green"
```

---

## Task 8: RUN the eval (orchestrator runbook — live API, no Qdrant)

> Executed by the orchestrator, not a subagent. Needs API keys in `.env`.

- [ ] **Step 1: Produce plans**

Run: `.venv/bin/python -m src.services.chat.eval.planner_chain_compare --step run`
Expected: lines per (model × question) + baseline; `_work_planner/results.json` grows. qwen uses plain JSON (no `json_schema`) so it should not hang; if a cell FAILS it is recorded, non-fatal.

- [ ] **Step 2: Judge + render**

Run: `.venv/bin/python -m src.services.chat.eval.planner_chain_compare --step judge`
Expected: `wrote .../2026-06-04-planner-chain-model-compare.md`.

- [ ] **Step 3: Append the Opus verdict**

Read the artifact (scores + plan dumps). Replace `> Opus verdict appended after manual review.` with a 2-3 paragraph verdict: which model produced the best decomposition/coverage, did the chain beat the single-call baseline, and the cost (3× calls) vs quality tradeoff. Edit in place.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/eval/_work_planner docs/superpowers/eval/2026-06-04-planner-chain-model-compare.md
git commit -m "eval(planner-chain): run results + artifact + verdict"
```

---

## Self-Review

**Spec coverage:**
- 3-step chain (decompose/expand/consolidate) — Tasks 1–2.
- App-case + related-framings guarantees in DECOMPOSE — Task 1 prompt + Task 1 test.
- Flag-gated dispatcher + single-call fallback — Task 3 (+ 3 routing tests).
- QueryPlan unchanged / downstream untouched — Task 3 returns `QueryPlan`; Task 3 Step 5 regression run.
- No `response_format` (qwen-safe) — `_planner_call` omits it; eval uses plain JSON.
- Eval: 3 models + baseline, 3 questions, 4 judge dims, tokens/USD/ms, one artifact — Tasks 6 & 8.
- Lockstep artifacts (backend, prompts, env flag, modal node, mermaid/doc 45, doc 54, invariants, changelog, tests) — Tasks 1–6.

**Placeholder scan:** all prompts and code are concrete; the only `TODO`-like marker is the deliberate "Opus verdict" placeholder line the eval writes and Task 8 replaces. The doc-54 mermaid fence note is explicit.

**Type consistency:** `QueryPlan(concepts, suggested_authors, queries, facets)` used consistently; JSON `perspectives` → `suggested_authors` in both `_parse_consolidate` and `_extract_concepts_single`. Chain step fn names (`_planner_decompose/_expand/_consolidate`) and parser names (`_parse_decompose/_expand/_consolidate`) match across Tasks 2, 3, 6. Eval row keys (`model/qi/label/plan_text/in_tok/out_tok/ms/ok/err/scores`) consistent across `_save_results`, `step_run`, `_render_artifact`.

**Real cost capture:** `step_run` calls each step via `_call_usage`, which reads
`resp.usage.{prompt_tokens,completion_tokens}`, so `in_tok/out_tok` are real and the
USD column is the true per-model spend for that model's chain (3 calls) vs the
baseline (1 call). Production code is untouched — the eval reuses DT's prompts +
parsers directly.
```
