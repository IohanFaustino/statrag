# Q&A Deepagent Rebuild (roster + thesis/body/conclusion + checker loop) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Q&A mode as a scoped agentic-retrieval deepagent — `scope → gate(simple‖compound) → orchestrator(retrieve‖analyst subagents) → organize → checker(re-call loop)` — emitting a fixed **thesis → body → conclusion** answer, with a 4-agent roster (each agent: `AGENTS.md` + tools + skills + `<task>`-scaffolded prompt) and 3 Open-Agent-Skills `SKILL.md` files.

**Architecture:** Two deterministic nano guardrails (scope pre-pass, checker post-loop) wrap a `deepagents==0.6.8` orchestrator. The orchestrator retrieves via a `search_corpus` tool that offloads hits to a `StoreBackend` virtual `/sources/`, guided by `grounded-qa` + `synthesize-progression` skills. Compound questions spawn one analyst `SubAgent` per sub-question (isolated context, `response_format=QAFinding`). A deterministic checker (`critique-coverage`) judges coverage + grounding and re-calls the orchestrator up to `QA_MAX_RECHECK` times. Any agent failure falls back to today's single-shot `hybrid_search`+generate. **Zero tutor files touched.**

**Tech Stack:** Python 3.12, `deepagents==0.6.8`, `langchain-openai` (`ChatOpenAI`), `langchain.agents.structured_output.ToolStrategy`, Qdrant hybrid retrieval, Pydantic v2, FastAPI SSE; React + Vite + TS + vitest frontend.

**Spec:** [`docs/superpowers/specs/2026-06-05-qa-deepagent-design.md`](../specs/2026-06-05-qa-deepagent-design.md) (revised 2026-06-08). **Supersedes** [`2026-06-05-qa-deepagent.md`](2026-06-05-qa-deepagent.md).

**Isolation rule (hard):** No imports from `deep_tutor.py`, `orchestrator_workers.py`, `ow_deepagents.py`, `prompts/deep_tutor.py`, `ow_skills/synthesis/`. Q&A owns `qa_skills/` + `qa_agents/`. Shared read-only primitives only: `TutorCitation`, `renderInlineWithCites`/`MathBlock`.

**Confirmed APIs (this session):** `deepagents` 0.6.8; construction idiom in `agents/ow_deepagents.py:59-136`; `SubAgent` TypedDict keys = `name, description, system_prompt, tools, model, skills, response_format`.

**Run tests with:** `.venv/bin/python -m pytest <path> -v` (backend), `cd web && npx vitest run <path>` (frontend).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/services/chat/schemas/output.py` | Modify | `QAScope`(+complexity/sub_questions); new `QAFinding`,`QACheck`; reshape `QAAnswer`→thesis/body/conclusion |
| `src/services/chat/schemas/__init__.py` | Modify | re-export `QAFinding`,`QACheck` |
| `src/services/chat/agents/qa_skills/{grounded-qa,synthesize-progression,critique-coverage}/SKILL.md` | Create | 3 skills |
| `src/services/chat/agents/qa_agents/{scope,orchestrator,analyst,checker}/AGENTS.md` | Create | 4 contracts |
| `src/services/chat/prompts/qa.py` | Rewrite | `QA_SCOPE_PROMPT`,`QA_AGENT_PROMPT`,`QA_ANALYST_PROMPT`,`QA_CHECK_PROMPT` |
| `src/services/chat/agents/qa.py` | Rewrite | store builder, `search_corpus`, agent builders, checker, gate+loop, `run_qa`, fallback |
| `web/src/types.ts` | Modify | QA types |
| `web/src/components/QAAnswerCard.tsx` | Modify | thesis→body→conclusion render |
| `web/src/data/qaPipeline.ts`, `web/src/components/QAPipelineDiagram.tsx` | Modify | node/edge reshape + loop edge |
| `web/src/components/MessageThread.tsx` | Modify | progress events |
| `web/src/components/modals/QAModeModal.tsx`, `web/src/data/qaMode.ts` | Modify | modal copy |
| `docs/services/chat-features/51-qa-mode.md` | Rewrite | feature doc |
| `docs/system/invariants.md`, `docs/system/changelog.md`, `docs/services/chat.md` | Modify | lockstep |

`router.py`, `modes.py`, `schemas/_core.py`: **no change** — regression test only (Task 8).

---

## Task 1: Schemas — QAScope/QAFinding/QACheck + reshape QAAnswer

**Files:** Modify `src/services/chat/schemas/output.py` (lines ~290-320), `src/services/chat/schemas/__init__.py`; Test `src/services/chat/tests/test_qa_schema.py`.

- [ ] **Step 1: Write failing test** — replace/extend `test_qa_schema.py`:

```python
def test_qascope_complexity_default_simple():
    from src.services.chat.schemas import QAScope
    s = QAScope(target_gap="why bias and variance trade off")
    assert s.complexity == "simple"
    assert s.sub_questions == []

def test_qascope_compound():
    from src.services.chat.schemas import QAScope
    s = QAScope(target_gap="x", complexity="compound", sub_questions=["a", "b"])
    assert s.complexity == "compound" and len(s.sub_questions) == 2

def test_qafinding_shape():
    from src.services.chat.schemas import QAFinding
    f = QAFinding(sub_question="what is bias", text="Bias is …")
    assert f.pertinent is True and f.citations == []

def test_qacheck_shape():
    from src.services.chat.schemas import QACheck
    c = QACheck(sufficient=False, gaps=["missing variance"])
    assert c.sufficient is False and c.gaps == ["missing variance"]

def test_qaanswer_progression_no_tutor_fields():
    from src.services.chat.schemas import QAAnswer, QAScope
    a = QAAnswer(thesis="t", body="b", conclusion="c", scope=QAScope(target_gap="x"))
    fields = set(QAAnswer.model_fields)
    assert {"thesis", "body", "conclusion"} <= fields
    assert {"text", "sections", "aspects", "figures"} & fields == set()
```

- [ ] **Step 2: Run to verify fail** — `.venv/bin/python -m pytest src/services/chat/tests/test_qa_schema.py -v` → FAIL (ImportError QAFinding/QACheck; QAAnswer.text still present).

- [ ] **Step 3: Edit `output.py`.** Replace `QAScope` (add two fields), replace `QAAnswer` (thesis/body/conclusion, drop `text`), add `QAFinding` + `QACheck`:

```python
class QAScope(BaseModel):
    """Parsed scope of a punctual question (drives the adaptive retrieval gate)."""
    target_gap: str
    assumed_known: list[str] = Field(default_factory=list)
    answer_form: Literal["explanation", "definition", "comparison",
                         "derivation", "yes_no", "list"] = "explanation"
    complexity: Literal["simple", "compound"] = "simple"
    sub_questions: list[str] = Field(default_factory=list)


class QAFinding(BaseModel):
    """One analyst subagent's grounded mini-finding (compound path; fused then discarded)."""
    sub_question: str
    text: str = ""
    citations: list[TutorCitation] = Field(default_factory=list)
    pertinent: bool = True


class QAAnswer(BaseModel):
    """Punctual Q&A answer as a fixed thesis → body → conclusion progression.

    Deliberately NOT tutor-shaped: exactly three content fields, no sections/
    aspects/figures. ``thesis`` is the answer-first core; ``body`` the augmented
    deep-dive (merged/deduped, inline ``[n]`` markers); ``conclusion`` the concise
    wrap. ``grounding`` carries the checker verdict {ok, unsupported[], confidence}.
    """
    thesis: str
    body: str
    conclusion: str
    scope: QAScope
    citations: list[TutorCitation] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)
    grounding: dict = Field(default_factory=dict)


class QACheck(BaseModel):
    """Checker verdict: drives the re-call loop."""
    sufficient: bool
    gaps: list[str] = Field(default_factory=list)
    grounding: dict = Field(default_factory=dict)
```

Delete the now-unused `QAGenerateOut`/`QAVerifyOut` only if no longer referenced after Task 7 (grep first; defer deletion to Task 8 cleanup if still imported). `TutorCitation`, `Literal`, `Field` already imported in this file.

- [ ] **Step 4:** In `schemas/__init__.py` add `QAFinding, QACheck,` to the import block (after `QAScope,`) and to `__all__`.

- [ ] **Step 5: Run to verify pass** — same pytest → PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/schemas/output.py src/services/chat/schemas/__init__.py src/services/chat/tests/test_qa_schema.py
git commit -m "feat(qa): QAScope+complexity, QAFinding, QACheck; reshape QAAnswer to thesis/body/conclusion"
```

---

## Task 2: 3 skills + 4 AGENTS.md + 4 prompts

**Files:** Create `src/services/chat/agents/qa_skills/{grounded-qa,synthesize-progression,critique-coverage}/SKILL.md`; create `src/services/chat/agents/qa_agents/{scope,orchestrator,analyst,checker}/AGENTS.md`; Rewrite `src/services/chat/prompts/qa.py`; Test `src/services/chat/tests/test_qa_prompts.py`.

- [ ] **Step 1: Write failing test** — `test_qa_prompts.py`:

```python
from pathlib import Path
SKILLS = Path("src/services/chat/agents/qa_skills")
AGENTS = Path("src/services/chat/agents/qa_agents")

def test_three_skills_open_agent_format():
    for name in ["grounded-qa", "synthesize-progression", "critique-coverage"]:
        t = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert t.startswith("---")
        assert f"name: {name}" in t
        assert "metadata:" in t and "version:" in t

def test_synthesize_skill_mentions_merge_and_progression():
    t = (SKILLS / "synthesize-progression" / "SKILL.md").read_text("utf-8").lower()
    assert "merge" in t and "thesis" in t and "conclusion" in t

def test_critique_skill_mentions_gaps_and_grounding():
    t = (SKILLS / "critique-coverage" / "SKILL.md").read_text("utf-8").lower()
    assert "gap" in t and "grounding" in t

def test_four_agents_md_nonempty():
    for name in ["scope", "orchestrator", "analyst", "checker"]:
        t = (AGENTS / name / "AGENTS.md").read_text(encoding="utf-8")
        assert len(t.strip()) > 80

def test_prompts_have_task_tokens():
    from src.services.chat.prompts import qa
    for const in [qa.QA_SCOPE_PROMPT, qa.QA_AGENT_PROMPT, qa.QA_ANALYST_PROMPT, qa.QA_CHECK_PROMPT]:
        assert "<task>" in const and "</task>" in const
    assert "complexity" in qa.QA_SCOPE_PROMPT and "sub_questions" in qa.QA_SCOPE_PROMPT
    assert "sufficient" in qa.QA_CHECK_PROMPT and "gaps" in qa.QA_CHECK_PROMPT
    assert "thesis" in qa.QA_AGENT_PROMPT and "conclusion" in qa.QA_AGENT_PROMPT
```

- [ ] **Step 2: Run to verify fail** — FAIL (files missing; prompt consts missing).

- [ ] **Step 3: Create the 3 SKILL.md.** Use Open Agent Skills frontmatter.

`qa_skills/grounded-qa/SKILL.md`:
```markdown
---
name: grounded-qa
description: Answer ONE scoped question from textbook sources via bounded agentic retrieval — pertinence to the central question, cite every claim, no tutor scaffolding.
metadata:
  version: "1.0.0"
---
# Grounded Q&A
## When to use
Answering a single punctual question grounded in retrieved textbook sources. Hits accumulate under `/sources/`.
## Instructions
1. Call `search_corpus` with a focused query for `target_gap`; read the briefs and `/sources/*.md`.
2. Coverage check: is `target_gap` answerable? If not, refine the query and call again. Stop at the round cap you are given.
3. Pertinence: keep only evidence serving the CENTRAL `target_gap`; discard tangents.
4. Skip everything in `assumed_known` — never define/explain/re-derive it.
5. PUNCTUAL: no recommendations, intuition asides, worked examples, or multi-section teaching — unless `answer_form` is `list`/`derivation`. This is NOT a tutor answer.
6. Cite every factual claim with inline `[n]` tied to `/sources/`.
7. Honesty: if the corpus lacks it, say so in one sentence, zero citations. Never fabricate.
## Output
Evidence in `/sources/`; the orchestrator emits `QAAnswer`, each analyst a `QAFinding`.
```

`qa_skills/synthesize-progression/SKILL.md`:
```markdown
---
name: synthesize-progression
description: Fuse grounded evidence/findings into a thesis → body → conclusion progression, merging or dropping repeated information.
metadata:
  version: "1.0.0"
---
# Synthesize progression
## When to use
Organizing gathered evidence (simple loop) or analyst findings (compound) into one answer.
## Instructions
1. **Merge or drop repeats.** When two findings overlap, merge into one statement; when they conflict, surface the conflict, do not silently drop.
2. **thesis** — the direct core answer to `target_gap`, 1–2 sentences, answer-first.
3. **body** — augmented connected detail expanding the thesis, ordered as a progression of ideas, inline `[n]` markers. Drop non-pertinent findings.
4. **conclusion** — concise wrap (1–2 sentences); no new facts.
5. Keep it punctual — this is NOT a tutor walkthrough; three fields only.
## Output
`QAAnswer{thesis, body, conclusion, citations, math_blocks}`.
```

`qa_skills/critique-coverage/SKILL.md`:
```markdown
---
name: critique-coverage
description: Audit a drafted answer for coverage of the question and grounding in sources; emit concrete gaps that trigger a bounded re-call.
metadata:
  version: "1.0.0"
---
# Critique coverage
## When to use
After the orchestrator drafts an answer, before finalizing.
## Instructions
1. Coverage: is `target_gap` fully and correctly answered by {thesis, body, conclusion}? Name concrete missing/under-covered points as `gaps`.
2. Grounding: is every claim supported by the numbered sources? List `unsupported`.
3. Decide `sufficient`: true only when no genuine coverage hole remains. Re-call for substance, never style.
4. Never add facts; never rewrite the draft.
## Output
`QACheck{sufficient, gaps[], grounding{ok, unsupported[], confidence}}`.
```

- [ ] **Step 4: Create the 4 AGENTS.md** (operating contracts).

`qa_agents/scope/AGENTS.md`:
```markdown
# Scope agent
**Mission:** Parse the question into QAScope. Extract, do not answer.
**Rules:** Prefer `complexity:"simple"`. `assumed_known` only from explicit "I know…/except…/I understand…" signals. `sub_questions` (2–4, focused, self-contained) only when compound. `target_gap` is the narrowed question, not the whole topic.
**Stop:** Emit QAScope JSON and nothing else.
```

`qa_agents/orchestrator/AGENTS.md`:
```markdown
# Orchestrator agent
**Mission:** Answer ONE question grounded in the textbooks, as thesis → body → conclusion.
**Skills:** invoke `grounded-qa` to retrieve; `synthesize-progression` to fuse.
**Rules:** Answer only `target_gap`; skip `assumed_known`. Never exceed the retrieval round cap. For compound questions, delegate each sub-question to its analyst via the `task` tool, then fuse — merge/drop repeats, drop non-pertinent findings. On a re-call, address the provided `gaps` first. Cite every claim. PUNCTUAL — never tutor-shaped.
**Stop:** Emit one `QAAnswer`.
```

`qa_agents/analyst/AGENTS.md`:
```markdown
# Analyst subagent
**Mission:** Research ONE sub-question in isolated context; report a grounded QAFinding.
**Skills:** `grounded-qa`.
**Rules:** Retrieve only for YOUR sub-question, but keep only evidence serving the CENTRAL question; set `pertinent=false` if off-target. Ground every claim with `[n]`; never invent sources.
**Stop:** Emit one `QAFinding`.
```

`qa_agents/checker/AGENTS.md`:
```markdown
# Checker agent
**Mission:** Audit the drafted answer for coverage + grounding; decide finalize vs re-call.
**Skills:** `critique-coverage`.
**Rules:** Name concrete `gaps`. Re-call only for genuine coverage holes, not stylistic nits. Never add facts or rewrite the draft.
**Stop:** Emit one `QACheck`.
```

- [ ] **Step 5: Rewrite `prompts/qa.py`** with the four `<task>`-scaffolded constants (verbatim from spec §3.3): `QA_SCOPE_PROMPT` (now emits `complexity`+`sub_questions`), `QA_AGENT_PROMPT`, `QA_ANALYST_PROMPT`, `QA_CHECK_PROMPT`. Each uses `<role>/<task>/<rules>[/<output_format>]`. Keep the module docstring + `from __future__ import annotations`. Remove the obsolete `QA_GENERATE_PROMPT`/`QA_VERIFY_PROMPT` only after Task 7 stops importing them (the fallback may reuse a generate prompt — keep a `QA_FALLBACK_GENERATE_PROMPT` that targets thesis/body/conclusion).

- [ ] **Step 6: Run to verify pass** — `test_qa_prompts.py` → PASS.

- [ ] **Step 7: Commit**

```bash
git add src/services/chat/agents/qa_skills src/services/chat/agents/qa_agents src/services/chat/prompts/qa.py src/services/chat/tests/test_qa_prompts.py
git commit -m "feat(qa): 3 Open-Agent skills, 4 AGENTS.md contracts, 4 <task>-scaffolded prompts"
```

---

## Task 3: `search_corpus` tool + asset store builder

**Files:** Modify `src/services/chat/agents/qa.py`; Test `src/services/chat/tests/test_qa_tool.py`, `test_qa_store.py`.

- [ ] **Step 1: Write failing tests** — `test_qa_tool.py`:

```python
from src.services.chat.schemas import Source

def _src(i, cid):
    return Source(rank=i, book="hansen", book_name="Hansen", authors_short="Hansen",
                  year=2022, chapter="ch07", section="7.1", title="Bias",
                  excerpt="ex", chunk="Bias is systematic error.", score=0.9, chunkId=cid)

def test_search_corpus_accumulates_and_dedups(monkeypatch):
    import src.services.chat.agents.qa as qa
    calls = {"n": 0}
    def fake(query, **kw):
        calls["n"] += 1
        return ([_src(1, "c1"), _src(2, "c2")], {"collections": ["x"]})
    monkeypatch.setattr(qa, "hybrid_search", fake)
    acc = {}
    tool = qa._make_search_corpus(book_slugs=["hansen"], acc=acc, k=4)
    out = tool.invoke({"query": "what is bias"})
    assert "Bias" in out and "[1]" in out
    assert set(acc) == {"c1", "c2"}
    tool.invoke({"query": "again"})
    assert set(acc) == {"c1", "c2"} and calls["n"] == 2
```

`test_qa_store.py`:
```python
def test_store_has_skills_and_agents():
    import src.services.chat.agents.qa as qa
    store = qa._store_with_assets()
    keys = {i.key for ns in [("filesystem",)] for i in store.search(ns)}
    for n in ["grounded-qa", "synthesize-progression", "critique-coverage"]:
        assert f"/skills/{n}/SKILL.md" in keys
    for n in ["scope", "orchestrator", "analyst", "checker"]:
        assert f"/agents/{n}/AGENTS.md" in keys
```
(If `InMemoryStore.search` signature differs, assert via `store.get(("filesystem",), key)` per key instead.)

- [ ] **Step 2: Run to verify fail** — FAIL (`_make_search_corpus`/`_store_with_assets` undefined).

- [ ] **Step 3: Implement in `qa.py`** (add imports `import asyncio`, `from pathlib import Path`; keep existing imports):

```python
create_deep_agent = None  # monkeypatch seam; real one lazy-imported in _cda()

_QA_MAX_ROUNDS = int(os.environ.get("QA_MAX_ROUNDS", "3"))
_QA_MAX_RECHECK = int(os.environ.get("QA_MAX_RECHECK", "2"))
_QA_DECOMPOSE = os.environ.get("QA_DECOMPOSE", "1") == "1"
_QA_CHECK = os.environ.get("QA_CHECK", "1") == "1"

_SKILLS = ["grounded-qa", "synthesize-progression", "critique-coverage"]
_AGENTS = ["scope", "orchestrator", "analyst", "checker"]
_ASSET_ROOT = Path(__file__).parent


def _brief_line(n: int, s: Source) -> str:
    body = (s.chunk or s.excerpt or "")[:_CHUNK_PREVIEW_CHARS]
    return f"[{n}] {s.book_name or s.book} · {s.chapter} {s.section} — {s.title}\n{body}"


def _make_search_corpus(*, book_slugs, acc: dict, k: int):
    from langchain.tools import tool as _tool
    @_tool
    def search_corpus(query: str) -> str:
        """Search the selected textbooks for passages relevant to `query`.
        Returns numbered source briefs. Call again with a refined query if the
        target gap is not yet covered."""
        sources, _ = hybrid_search(query, book_slugs=book_slugs, top_k=max(1, k),
                                   rerank=True, rerank_top_n=max(1, k),
                                   adjacent_sections=False)
        lines = []
        for s in sources:
            if s.chunkId in acc:
                continue
            acc[s.chunkId] = s
            lines.append(_brief_line(len(acc), s))
        return "\n\n".join(lines) if lines else "No new passages found for that query."
    return search_corpus


def _store_with_assets():
    """InMemoryStore preloaded with the 3 skills + 4 AGENTS.md contracts."""
    from deepagents.backends.utils import create_file_data
    from langgraph.store.memory import InMemoryStore
    store = InMemoryStore()
    for n in _SKILLS:
        md = (_ASSET_ROOT / "qa_skills" / n / "SKILL.md").read_text(encoding="utf-8")
        store.put(namespace=("filesystem",), key=f"/skills/{n}/SKILL.md",
                  value=create_file_data(md))
    for n in _AGENTS:
        md = (_ASSET_ROOT / "qa_agents" / n / "AGENTS.md").read_text(encoding="utf-8")
        store.put(namespace=("filesystem",), key=f"/agents/{n}/AGENTS.md",
                  value=create_file_data(md))
    return store


def _cda():
    if create_deep_agent is not None:
        return create_deep_agent
    from deepagents import create_deep_agent as _real
    return _real


def _lc_model(model):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model or settings.openai_model_nano, temperature=0.0,
                      api_key=settings.openai_api_key)


async def _run_structured(agent, user_content: str):
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user", "content": user_content}]},
        {"configurable": {"thread_id": "qa"}})
    return result.get("structured_response") if isinstance(result, dict) else None
```

(`hybrid_search`, `Source`, `_CHUNK_PREVIEW_CHARS`, `settings`, `os` already present.)

- [ ] **Step 4: Run to verify pass** — both test files PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/tests/test_qa_tool.py src/services/chat/tests/test_qa_store.py
git commit -m "feat(qa): search_corpus dedup tool + asset store (skills + AGENTS.md)"
```

---

## Task 4: Scope pre-pass emits complexity + sub_questions

**Files:** Modify `extract_scope` in `qa.py`; Test `src/services/chat/tests/test_qa_scope.py`.

- [ ] **Step 1: Write failing test:**

```python
import json, pytest

@pytest.mark.asyncio
async def test_scope_parses_compound(monkeypatch):
    import src.services.chat.agents.qa as qa
    async def fake(messages, **kw):
        return json.dumps({"target_gap": "how X relates to Y", "assumed_known": [],
                           "answer_form": "explanation", "complexity": "compound",
                           "sub_questions": ["what is X", "what is Y"]})
    monkeypatch.setattr(qa, "_chat", fake)
    s = await qa.extract_scope("what are X and Y and how relate?")
    assert s.complexity == "compound" and s.sub_questions == ["what is X", "what is Y"]

@pytest.mark.asyncio
async def test_scope_failopen_simple(monkeypatch):
    import src.services.chat.agents.qa as qa
    async def boom(messages, **kw): raise RuntimeError("down")
    monkeypatch.setattr(qa, "_chat", boom)
    s = await qa.extract_scope("why bias and variance trade off")
    assert s.complexity == "simple" and s.sub_questions == []
    assert s.target_gap == "why bias and variance trade off"
```

- [ ] **Step 2: Run to verify fail** — FAIL (fields ignored).

- [ ] **Step 3: Edit `extract_scope`** — update `fallback` to include `complexity="simple", sub_questions=[]`; in the try-block after `data = json.loads(...)`:

```python
        complexity = data.get("complexity") if data.get("complexity") in {"simple", "compound"} else "simple"
        subs = [str(x).strip() for x in (data.get("sub_questions") or []) if str(x).strip()]
        if complexity != "compound":
            subs = []
        return QAScope(
            target_gap=str(data.get("target_gap") or query).strip(),
            assumed_known=[str(x).strip() for x in (data.get("assumed_known") or []) if str(x).strip()],
            answer_form=data.get("answer_form") if data.get("answer_form") in {
                "explanation", "definition", "comparison", "derivation", "yes_no", "list"} else "explanation",
            complexity=complexity, sub_questions=subs)
```

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/tests/test_qa_scope.py
git commit -m "feat(qa): scope pre-pass emits complexity + sub_questions (fail-open simple)"
```

---

## Task 5: Orchestrator — simple path deepagent

**Files:** Modify `qa.py` (add `answer_simple`); Test `src/services/chat/tests/test_qa_simple.py`.

- [ ] **Step 1: Write failing test:**

```python
import pytest
from src.services.chat.schemas import QAScope, QAAnswer

class _FakeAgent:
    def __init__(self, ans, sink=None): self._a, self._sink = ans, sink
    def invoke(self, inp, config):
        if self._sink is not None: self._sink["user"] = inp["messages"][0]["content"]
        return {"structured_response": self._a}

@pytest.mark.asyncio
async def test_answer_simple_returns_progression(monkeypatch):
    import src.services.chat.agents.qa as qa
    scope = QAScope(target_gap="why bias and variance trade off")
    expected = QAAnswer(thesis="Reducing one raises the other [1].", body="…", conclusion="…", scope=scope)
    sink = {}
    monkeypatch.setattr(qa, "create_deep_agent", lambda **kw: _FakeAgent(expected, sink), raising=False)
    ans = await qa.answer_simple(scope, book_slugs=["hansen"], acc={}, gaps=["needs variance"])
    assert isinstance(ans, QAAnswer) and ans.thesis.startswith("Reducing")
    assert "needs variance" in sink["user"]  # gaps forwarded on re-call
```

- [ ] **Step 2: Run to verify fail** — FAIL (`answer_simple` undefined).

- [ ] **Step 3: Implement `answer_simple`:**

```python
def _user_msg(scope, gaps):
    base = (f"Central question (target_gap): {scope.target_gap}\n"
            f"assumed_known: {json.dumps(scope.assumed_known)}\n"
            f"answer_form: {scope.answer_form}\n"
            f"Retrieval cap: {_QA_MAX_ROUNDS} search_corpus calls.\n")
    if gaps:
        base += f"PRIOR GAPS to address first: {json.dumps(gaps)}\n"
    return base


async def answer_simple(scope, *, book_slugs, acc: dict, model=None, gaps=None) -> "QAAnswer":
    from deepagents.backends import StoreBackend
    from langchain.agents.structured_output import ToolStrategy
    from src.services.chat.prompts.qa import QA_AGENT_PROMPT
    store = _store_with_assets()
    search = _make_search_corpus(book_slugs=book_slugs, acc=acc, k=_QA_TOP_K)
    agent = _cda()(model=_lc_model(model), tools=[search], system_prompt=QA_AGENT_PROMPT,
                   backend=lambda rt: StoreBackend(rt), store=store, skills=["/skills/"],
                   response_format=ToolStrategy(QAAnswer, handle_errors=True))
    ans = await _run_structured(agent, _user_msg(scope, gaps) +
                                "Gather evidence with search_corpus, then emit the QAAnswer.")
    if isinstance(ans, QAAnswer):
        return ans.model_copy(update={"scope": scope})
    raise RuntimeError("simple agent returned no structured QAAnswer")
```

(Import `QAAnswer` already at module top.)

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/tests/test_qa_simple.py
git commit -m "feat(qa): orchestrator simple-path deepagent (search loop → thesis/body/conclusion)"
```

---

## Task 6: Compound path — analyst subagents + organize

**Files:** Modify `qa.py` (add `answer_compound`); Test `src/services/chat/tests/test_qa_compound.py`.

- [ ] **Step 1: Write failing test:**

```python
import pytest
from src.services.chat.schemas import QAScope, QAAnswer, QAFinding

class _FakeAgent:
    def __init__(self, ans): self._a = ans
    def invoke(self, inp, config): return {"structured_response": self._a}

@pytest.mark.asyncio
async def test_compound_builds_one_subagent_per_subq(monkeypatch):
    import src.services.chat.agents.qa as qa
    scope = QAScope(target_gap="how X and Y relate", complexity="compound",
                    sub_questions=["what is X", "what is Y"])
    cap = {}
    def fake_cda(**kw):
        cap["subagents"] = kw.get("subagents")
        return _FakeAgent(QAAnswer(thesis="X,Y relate via Z [1].", body="…", conclusion="…", scope=scope))
    monkeypatch.setattr(qa, "create_deep_agent", fake_cda, raising=False)
    ans = await qa.answer_compound(scope, book_slugs=["hansen"], acc={})
    assert isinstance(ans, QAAnswer)
    subs = cap["subagents"]
    assert len(subs) == 2
    assert subs[0]["response_format"] is QAFinding
    assert subs[0]["skills"] == ["/skills/"] and len(subs[0]["tools"]) == 1
```

- [ ] **Step 2: Run to verify fail** — FAIL (`answer_compound` undefined).

- [ ] **Step 3: Implement `answer_compound`:**

```python
async def answer_compound(scope, *, book_slugs, acc: dict, model=None,
                          analyst_model=None, gaps=None) -> "QAAnswer":
    from deepagents.backends import StoreBackend
    from langchain.agents.structured_output import ToolStrategy
    from src.services.chat.prompts.qa import QA_AGENT_PROMPT, QA_ANALYST_PROMPT
    from src.services.chat.schemas import QAFinding
    store = _store_with_assets()
    search = _make_search_corpus(book_slugs=book_slugs, acc=acc, k=_QA_TOP_K)
    subagents = [{
        "name": f"analyst-{i + 1}",
        "description": f"Research a sub-question and report a grounded QAFinding: {sq}",
        "system_prompt": (QA_ANALYST_PROMPT + f"\n\nCENTRAL question: {scope.target_gap}"
                          + f"\nYOUR sub-question: {sq}"),
        "tools": [search], "skills": ["/skills/"],
        "model": analyst_model or settings.openai_model_nano,
        "response_format": QAFinding,
    } for i, sq in enumerate(scope.sub_questions)]
    sub_list = "; ".join(f"analyst-{i + 1} → {sq}" for i, sq in enumerate(scope.sub_questions))
    agent = _cda()(
        model=_lc_model(model), tools=[search], subagents=subagents,
        system_prompt=(QA_AGENT_PROMPT + "\n\nDelegate each sub-question to its analyst via the "
                       "task tool, then FUSE the findings into ONE answer to the CENTRAL question "
                       "(merge or drop repeated info; drop non-pertinent). Do not list sub-questions."),
        backend=lambda rt: StoreBackend(rt), store=store, skills=["/skills/"],
        response_format=ToolStrategy(QAAnswer, handle_errors=True))
    ans = await _run_structured(agent, _user_msg(scope, gaps) +
                                f"Sub-questions & analysts: {sub_list}\nDelegate, then emit the fused QAAnswer.")
    if isinstance(ans, QAAnswer):
        return ans.model_copy(update={"scope": scope})
    raise RuntimeError("compound agent returned no structured QAAnswer")
```

> **Concurrency note:** `task`-delegated `SubAgent`s run sequentially in deepagents 0.6.8. If live latency is poor, follow spec §13 — run analysts via `asyncio.gather` over per-analyst single-agent runs, then pass findings to an organize-only main agent. Keep `task`-delegation for v1; flag in the doc.

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/tests/test_qa_compound.py
git commit -m "feat(qa): compound-path analyst subagents → fused thesis/body/conclusion"
```

---

## Task 7: Checker + re-call loop + gate + fallback + progress events

**Files:** Modify `qa.py` (`check_answer`, `_fallback_answer`, rewrite `run_qa`); Test `test_qa_recheck.py`, `test_qa_fallback.py`, extend `test_qa_run.py`.

- [ ] **Step 1: Write failing tests** — `test_qa_recheck.py`:

```python
import pytest
from src.services.chat.schemas import ChatRequest, QAScope, QAAnswer, QACheck, Source

def _src(cid):
    return Source(rank=1, book="hansen", book_name="Hansen", authors_short="H", year=2022,
                  chapter="ch07", section="7.1", title="Bias", excerpt="ex",
                  chunk="Bias is systematic error.", score=0.9, chunkId=cid)

@pytest.mark.asyncio
async def test_recheck_loops_then_finalizes(monkeypatch):
    import src.services.chat.agents.qa as qa
    async def scope(q, **kw): return QAScope(target_gap=q, complexity="simple")
    monkeypatch.setattr(qa, "extract_scope", scope)
    async def resolve(*a, **k):
        from src.services.chat.agents._scope import BookResolution
        return BookResolution(book_slug="hansen", candidates=[], confidence=1.0, reason="")
    monkeypatch.setattr(qa, "resolve_book", resolve)
    monkeypatch.setattr(qa, "maybe_clarify", lambda *a, **k: None)
    monkeypatch.setattr(qa, "parse_catalog", lambda: [])
    monkeypatch.setattr(qa, "hybrid_search", lambda q, **kw: ([_src("c1")], {"collections": []}))
    calls = {"n": 0}
    async def simple(scope, **kw):
        calls["n"] += 1
        return QAAnswer(thesis=f"t{calls['n']}", body="b", conclusion="c", scope=scope)
    monkeypatch.setattr(qa, "answer_simple", simple)
    checks = iter([QACheck(sufficient=False, gaps=["g"]), QACheck(sufficient=True)])
    async def check(*a, **k): return next(checks)
    monkeypatch.setattr(qa, "check_answer", check)
    req = ChatRequest(message="why bias trades off", mode="qa", bookFilter=["hansen"])
    events = [e async for e in qa.run_qa(req)]
    assert calls["n"] == 2  # re-called once
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["data"]["thesis"] == "t2" and events[-1]["type"] == "done"
```

`test_qa_fallback.py` (agent explodes → deterministic fallback):
```python
import pytest
from src.services.chat.schemas import ChatRequest, QAScope, QAAnswer, Source

def _src(cid):
    return Source(rank=1, book="hansen", book_name="Hansen", authors_short="H", year=2022,
                  chapter="ch07", section="7.1", title="Bias", excerpt="ex",
                  chunk="Bias is systematic error.", score=0.9, chunkId=cid)

@pytest.mark.asyncio
async def test_run_qa_falls_back_on_agent_error(monkeypatch):
    import src.services.chat.agents.qa as qa
    async def scope(q, **kw): return QAScope(target_gap=q, complexity="simple")
    monkeypatch.setattr(qa, "extract_scope", scope)
    async def resolve(*a, **k):
        from src.services.chat.agents._scope import BookResolution
        return BookResolution(book_slug="hansen", candidates=[], confidence=1.0, reason="")
    monkeypatch.setattr(qa, "resolve_book", resolve)
    monkeypatch.setattr(qa, "maybe_clarify", lambda *a, **k: None)
    monkeypatch.setattr(qa, "parse_catalog", lambda: [])
    monkeypatch.setattr(qa, "hybrid_search", lambda q, **kw: ([_src("c1")], {"collections": []}))
    async def boom(*a, **k): raise RuntimeError("deepagents down")
    monkeypatch.setattr(qa, "answer_simple", boom)
    async def fb(scope, sources, req):
        return QAAnswer(thesis="fallback [1]", body="b", conclusion="c", scope=scope)
    monkeypatch.setattr(qa, "_fallback_answer", fb)
    monkeypatch.setattr(qa, "_QA_CHECK", False)
    req = ChatRequest(message="why bias trades off", mode="qa", bookFilter=["hansen"])
    events = [e async for e in qa.run_qa(req)]
    so = next(e for e in events if e["type"] == "structured_output")
    assert "fallback" in so["data"]["thesis"] and events[-1]["type"] == "done"
```

(Adjust `BookResolution` import/fields to the real class in `agents/_scope.py`.)

- [ ] **Step 2: Run to verify fail** — FAIL (`check_answer`/`_fallback_answer` undefined; `run_qa` not gated).

- [ ] **Step 3: Implement `check_answer` + `_fallback_answer`:**

```python
async def check_answer(scope, answer: "QAAnswer", sources, *, model=None) -> "QACheck":
    from src.services.chat.prompts.qa import QA_CHECK_PROMPT
    from src.services.chat.schemas import QACheck
    chosen = model or settings.openai_model_nano
    user = (f"target_gap: {scope.target_gap}\n\ndraft:\nTHESIS: {answer.thesis}\n"
            f"BODY: {answer.body}\nCONCLUSION: {answer.conclusion}\n\n"
            f"sources:\n{_sources_block(sources)}")
    try:
        raw = await _chat([{"role": "system", "content": QA_CHECK_PROMPT},
                           {"role": "user", "content": user}],
                          model=chosen, max_tokens=500, schema=QACheck)
        data = json.loads(strip_fences(raw))
        return QACheck(sufficient=bool(data.get("sufficient", True)),
                       gaps=[str(g) for g in (data.get("gaps") or [])],
                       grounding={"ok": bool(data.get("grounding", {}).get("ok", False)),
                                  "unsupported": [str(u) for u in data.get("grounding", {}).get("unsupported", [])],
                                  "confidence": float(data.get("grounding", {}).get("confidence", 0.5))})
    except Exception:  # noqa: BLE001
        logger.exception("qa.check_answer failed; fail-open sufficient")
        return QACheck(sufficient=True, gaps=[],
                       grounding={"ok": False, "unsupported": [], "confidence": 0.5})


async def _fallback_answer(scope, sources, req) -> "QAAnswer":
    """Deterministic regression-safety: single retrieval already done → nano generate
    into thesis/body/conclusion via QA_FALLBACK_GENERATE_PROMPT."""
    from src.services.chat.prompts.qa import QA_FALLBACK_GENERATE_PROMPT
    user = (f"target_gap: {scope.target_gap}\nassumed_known: {json.dumps(scope.assumed_known)}\n"
            f"answer_form: {scope.answer_form}\n\nsources:\n{_sources_block(sources)}")
    raw = await _chat([{"role": "system", "content": QA_FALLBACK_GENERATE_PROMPT},
                       {"role": "user", "content": user}],
                      model=_model_for("agent", req), max_tokens=900, schema=QAAnswer)
    data = json.loads(strip_fences(raw))
    return QAAnswer(thesis=str(data.get("thesis", "")), body=str(data.get("body", "")),
                    conclusion=str(data.get("conclusion", "")), scope=scope,
                    citations=_coerce_citations(data.get("citations")),
                    math_blocks=[str(m) for m in (data.get("math_blocks") or []) if str(m).strip()],
                    grounding={"ok": True, "unsupported": [], "confidence": 0.6})
```

Add `QA_FALLBACK_GENERATE_PROMPT` to `prompts/qa.py` (Task 2 already created the file; add this constant there — `<role>/<task>/<output_format>` returning `{thesis, body, conclusion, citations, math_blocks}`).

- [ ] **Step 4: Rewrite `run_qa` tail.** Keep everything through the corpus-miss block. Replace the old generate/verify `try` block with the gate+loop:

```python
    acc: dict = {s.chunkId: s for s in sources}
    gaps = None
    try:
        for rnd in range(1, _QA_MAX_RECHECK + 1):
            if scope.complexity == "compound" and _QA_DECOMPOSE and scope.sub_questions:
                yield {"type": "progress", "stage": ("rechecking" if rnd > 1 else "analyzing"),
                       "round": rnd, "subQuestions": scope.sub_questions}
                answer = await answer_compound(scope, book_slugs=book_slugs, acc=acc, gaps=gaps,
                                               model=_model_for("agent", req),
                                               analyst_model=_model_for("analyst", req))
            else:
                yield {"type": "progress", "stage": ("rechecking" if rnd > 1 else "retrieving"), "round": rnd}
                answer = await answer_simple(scope, book_slugs=book_slugs, acc=acc, gaps=gaps,
                                             model=_model_for("agent", req))
            if not _QA_CHECK:
                if not answer.grounding:
                    answer = answer.model_copy(update={"grounding": {"ok": True, "unsupported": [], "confidence": 0.7}})
                break
            chk = await check_answer(scope, answer, list(acc.values()), model=_model_for("check", req))
            answer = answer.model_copy(update={"grounding": chk.grounding})
            if chk.sufficient or rnd == _QA_MAX_RECHECK:
                break
            gaps = chk.gaps
    except Exception:  # noqa: BLE001
        logger.exception("qa agent path failed; deterministic fallback")
        try:
            answer = await _fallback_answer(scope, sources, req)
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "code": type(exc).__name__, "message": str(exc)}
            yield {"type": "done"}
            return
    sources = list(acc.values())
```

The existing SSE tail (`structured_output{schema:"QAAnswer", data: answer.model_dump()}` → `sources_full` → `retrieval_meta` → `usage` → `done`) is unchanged and now renders accumulated `sources`. Update the corpus-miss `QAAnswer(...)` construction to the new fields (`thesis=honest sentence, body="", conclusion=""`).

- [ ] **Step 5: Run to verify pass** — `pytest test_qa_recheck.py test_qa_fallback.py test_qa_run.py -v` → PASS (repair `test_qa_run.py` assertions that referenced the old single-generate path / `text`).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/prompts/qa.py src/services/chat/tests/test_qa_recheck.py src/services/chat/tests/test_qa_fallback.py src/services/chat/tests/test_qa_run.py
git commit -m "feat(qa): checker + env-capped re-call loop + gate + deterministic fallback + progress events"
```

---

## Task 8: Stage models + suite green + isolation grep

**Files:** Modify `qa.py` (`_model_for` already generic — confirm `agent`/`analyst`/`check` keys); Test `test_qa_stage_models.py`; clean up obsolete tests.

- [ ] **Step 1: Write failing test:**

```python
def test_model_for_check_env(monkeypatch):
    import src.services.chat.agents.qa as qa
    from src.services.chat.schemas import ChatRequest
    monkeypatch.setenv("QA_CHECK_MODEL", "gpt-5.4-nano-2026-03-17")
    assert qa._model_for("check", ChatRequest(message="x", mode="qa")) == "gpt-5.4-nano-2026-03-17"

def test_model_for_stagemodels_override():
    import src.services.chat.agents.qa as qa
    from src.services.chat.schemas import ChatRequest
    req = ChatRequest(message="x", mode="qa", stageModels={"analyst": "deepseek-chat"})
    assert qa._model_for("analyst", req) == "deepseek-chat"
```

- [ ] **Step 2: Run** — PASS (generic resolver). Keep as regression guard.

- [ ] **Step 3: Clean obsolete tests** — update/remove `test_qa_nodes.py`, `test_qa_clarify.py`, `test_qa_gate.py`, `test_qa_xml_scaffold.py`, `test_qa_schemas.py` references to removed `generate_scoped`/`QAGenerateOut`/`QAVerifyOut`/`text`. Do not lose coverage — port assertions to the new helpers.

- [ ] **Step 4: Full suite + isolation grep:**

```bash
.venv/bin/python -m pytest src/services/chat/tests/ -k "qa or mode_routing or mode_parity" -v
grep -rn "deep_tutor\|orchestrator_workers\|ow_deepagents\|ow_skills" src/services/chat/agents/qa.py src/services/chat/prompts/qa.py
```
Expected: tests PASS; grep empty (exit 1).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/tests/
git commit -m "test(qa): stage-model resolution (agent/analyst/check) + obsolete-test cleanup + isolation grep"
```

---

## Task 9: Frontend lockstep

**Files:** Modify `web/src/types.ts`, `QAAnswerCard.tsx`, `data/qaPipeline.ts`, `QAPipelineDiagram.tsx`, `MessageThread.tsx`, `modals/QAModeModal.tsx`, `data/qaMode.ts`; Tests `types.qa.test.ts`, `qaPipeline.test.ts`, `QAPipelineDiagram.test.tsx`, `QAAnswerCard.test.tsx`.

- [ ] **Step 1: Write failing tests** — `types.qa.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import type { QAAnswer, QAScope, QAFinding, QACheck } from "./types";
describe("QA types", () => {
  it("QAAnswer is a thesis/body/conclusion progression", () => {
    const a: QAAnswer = { thesis: "t", body: "b", conclusion: "c",
      scope: { target_gap: "x", assumed_known: [], answer_form: "explanation",
               complexity: "simple", sub_questions: [] }, citations: [], math_blocks: [], grounding: {} };
    expect(a.thesis && a.body && a.conclusion).toBeTruthy();
  });
  it("QAFinding + QACheck exist", () => {
    const f: QAFinding = { sub_question: "a", text: "t", citations: [], pertinent: true };
    const c: QACheck = { sufficient: false, gaps: ["g"], grounding: {} };
    expect(f.pertinent && !c.sufficient).toBe(true);
  });
});
```

`qaPipeline.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { QA_PIPELINE } from "./qaPipeline";
describe("QA pipeline graph", () => {
  it("has agentic nodes + checker loop edge", () => {
    const ids = QA_PIPELINE.nodes.map(n => n.id);
    for (const id of ["scope", "gate", "simple", "compound", "organize", "checker"]) expect(ids).toContain(id);
    expect(QA_PIPELINE.edges.some(e => e.from === "checker" && e.to === "organize")).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: `types.ts`** — `QAScope` += `complexity: "simple"|"compound"`, `sub_questions: string[]`; add `QAFinding`, `QACheck`; replace `QAAnswer` with `{ thesis, body, conclusion, scope, citations, math_blocks, grounding }` (drop `text`).

- [ ] **Step 4: `QAAnswerCard.tsx`** — render: thesis (emphasized `<p className="qa-card__thesis">`), body via existing `renderInlineWithCites` + `MathBlock`, conclusion (`<p className="qa-card__conclusion">`), grounding badge, optional `{scope.complexity === "compound" && scope.sub_questions.length > 0 && <p className="qa-card__subhint">Answered via {scope.sub_questions.length} sub-questions</p>}`.

- [ ] **Step 5: `qaPipeline.ts` + `QAPipelineDiagram.tsx`** — node union `"scope"|"gate"|"simple"|"compound"|"organize"|"checker"|"clarify"`; nodes per spec §10 (llm: scope/simple/compound/organize/checker `defaultModel: "gpt-5.4-nano-2026-03-17"`; data: gate/clarify `"—"`); edges incl. `scope→clarify`, `scope→gate`, `gate→simple`, `gate→compound`, `simple→organize`, `compound→organize`, `organize→checker`, and the loop `checker→organize`. Update diagram render/test-ids to new node order.

- [ ] **Step 6: `MessageThread.tsx`** — on `type==="progress"` show transient status (`retrieving`→"Retrieving…", `analyzing`→`Analyzing ${subQuestions.length} sub-questions…`, `rechecking`→`Re-checking (round ${round})…`); clear on `structured_output`. Keep `schema==="QAAnswer"` → `<QAAnswerCard>`.

- [ ] **Step 7: `QAModeModal.tsx` + `qaMode.ts`** — copy → agentic pipeline (roster, gate, checker loop).

- [ ] **Step 8: Run frontend tests** — `cd web && npx vitest run src/types.qa.test.ts src/data/qaPipeline.test.ts src/components/QAPipelineDiagram.test.tsx src/components/QAAnswerCard.test.tsx` → PASS.

- [ ] **Step 9: Commit**

```bash
git add web/src
git commit -m "feat(qa-web): thesis/body/conclusion card, QAFinding/QACheck types, agentic diagram + checker loop, progress events"
```

---

## Task 10: Docs lockstep + required-elements verification + browser verify

**Files:** Rewrite `docs/services/chat-features/51-qa-mode.md`; Modify `docs/system/invariants.md`, `docs/system/changelog.md`, `docs/services/chat.md`.

- [ ] **Step 1: Rewrite `51-qa-mode.md`** — architecture (scope→gate→{simple‖compound}→organize→checker loop), mermaid matching `qaPipeline.ts` edges, env table (§8 spec), agent roster (§3 spec), "Deepagents features used", isolation note, SSE + progress events, synced-artifacts checklist (skills, AGENTS.md, new tests).

- [ ] **Step 2: Changelog** — append dated entry: "Q&A rebuilt as scoped agentic-retrieval deepagent — 4-agent roster (scope/orchestrator/analyst/checker), 3 Open-Agent skills, AGENTS.md contracts, thesis/body/conclusion output, env-capped checker re-call loop, deterministic fallback. No tutor files touched." Reference spec + this plan.

- [ ] **Step 3: Invariant** — add: "Q&A emits only `QAAnswer{thesis,body,conclusion}` (no `text`/`sections`/`aspects`/`figures`) and never imports tutor modules." Include grep: `grep -rn "deep_tutor\|orchestrator_workers\|ow_deepagents\|ow_skills" src/services/chat/agents/qa.py src/services/chat/prompts/qa.py` → empty.

- [ ] **Step 4: `chat.md`** — update Q&A row to the agentic pipeline, point to `51-qa-mode.md`.

- [ ] **Step 5: Required-elements verification (TodoWrite, one item each).** Tick every box in the spec §11 checklist: 4 agents × {element wired, description, AGENTS.md loaded, tools bound, skills loaded, `<task>` prompt, schema}; 3 skills; behaviour (thesis/body/conclusion, gate, checker loop, merge/drop, citations+badge, fallback, isolation grep); external-skill provenance (SKILL.md format, decompose→synthesize→verify, critique loop).

- [ ] **Step 6: Full suites + browser verify** —
```bash
.venv/bin/python -m pytest src/services/chat/tests/ -q
cd web && npx vitest run
```
Then `./scripts/dev.sh` → `http://localhost:5175` → Q&A, scope Hansen:
1. Simple: "why do bias and variance trade off?" → thesis/body/conclusion, cited, no tutor scaffolding.
2. Compound: "what are bias and variance and how do they trade off?" → one fused answer + "answered via N sub-questions".
3. Open the Q&A `(i)` modal → new node graph + checker loop renders; matches `docs/common ground/Elements/index.html`.
Diagnose with nano (OpenAI), not Groq, to avoid JSON flakiness masking logic.

- [ ] **Step 7: Commit**

```bash
git add docs/
git commit -m "docs(qa): lockstep — rewrite feature 51, changelog, invariant, chat.md for agentic Q&A roster"
```

---

## Self-Review

- **Spec coverage:** scope+gate (T4/T7); search_corpus + store (T3); simple (T5); compound subagents (T6); 3 skills + 4 AGENTS.md + 4 prompts (T2); QAScope/QAFinding/QACheck + thesis/body/conclusion QAAnswer (T1); checker re-call loop + fallback (T7); stage models (T8); frontend incl. loop edge (T9); docs + required-elements checklist + isolation invariant (T10). All spec §§ mapped.
- **Type consistency:** `answer_simple`/`answer_compound`/`check_answer`/`_fallback_answer` signatures and `QAAnswer{thesis,body,conclusion}` / `QACheck{sufficient,gaps,grounding}` used identically across tasks. `gaps` forwarded as `list[str]|None`.
- **Isolation:** T8 + T10 grep enforce no tutor imports; no task edits a tutor file.
- **No regression:** T7 deterministic fallback guarantees a `QAAnswer` even if deepagents fails.
- **Test seam:** every deepagent task monkeypatches `qa.create_deep_agent` (module attr default `None`) — no live LLM in units.
