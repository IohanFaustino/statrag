# Q&A Deepagent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Q&A mode as a scoped agentic-retrieval deepagent — deterministic scope → adaptive gate (simple bounded loop ‖ compound parallel subagents) → organize → deterministic verify — that grounds answers better while staying punctual.

**Architecture:** A deterministic nano scope pre-pass classifies `simple`/`compound` and emits sub-questions. A `deepagents` agent (own module, no tutor imports) owns retrieval via a `search_corpus` tool that offloads hits to a `StoreBackend` virtual `/sources/` FS, guided by a standalone `grounded-qa` skill, emitting `QAAnswer` via `ToolStrategy`. Compound questions spawn one analyst subagent per sub-question. A deterministic nano verify post-pass sets the grounding badge. Any agent failure falls back to today's single-shot `hybrid_search`+generate so behaviour never regresses.

**Tech Stack:** Python 3.12, `deepagents==0.6.8`, `langchain-openai` (`ChatOpenAI`), `langchain.agents.structured_output.ToolStrategy`, Qdrant hybrid retrieval, Pydantic v2, FastAPI SSE; React + Vite + TS + vitest frontend.

**Spec:** [`docs/superpowers/specs/2026-06-05-qa-deepagent-design.md`](../specs/2026-06-05-qa-deepagent-design.md)

**Isolation rule (hard):** This plan touches ZERO tutor files. No imports from `deep_tutor.py`, `orchestrator_workers.py`, `ow_deepagents.py`, `prompts/deep_tutor.py`, or `ow_skills/synthesis/`. Q&A gets its own `qa_skills/grounded-qa/`. Only shared primitives: read-only `TutorCitation` type and the `renderInlineWithCites`/`MathBlock` render helpers.

**Run tests with:** `.venv/bin/python -m pytest <path> -v` (backend), `cd web && npx vitest run <path>` (frontend).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/services/chat/schemas/output.py` | `QAScope` (+complexity/sub_questions), new `QAFinding` | Modify |
| `src/services/chat/schemas/__init__.py` | re-export `QAFinding` | Modify |
| `src/services/chat/agents/qa_skills/grounded-qa/SKILL.md` | grounding + anti-tutor-drift discipline | Create |
| `src/services/chat/prompts/qa.py` | scope prompt += complexity/sub-questions; agent system prompt | Modify |
| `src/services/chat/agents/qa.py` | rebuilt: tool, agent builders, gate, run_qa, fallback | Rewrite |
| `web/src/types.ts` | `QAScope` fields, `QAFinding` interface | Modify |
| `web/src/data/qaPipeline.ts` | reshaped node/edge graph | Modify |
| `web/src/components/QAPipelineDiagram.tsx` | render new nodes | Modify |
| `web/src/components/QAAnswerCard.tsx` | optional complexity hint | Modify |
| `web/src/components/MessageThread.tsx` | progress-event handling | Modify |
| `docs/system/invariants.md`, `docs/system/changelog.md`, `docs/services/chat.md`, `docs/services/chat-features/51-qa-mode.md` | lockstep docs | Modify |

`router.py`, `modes.py`, `schemas/_core.py` need **no change** (mode `qa` already routed/registered; `stageModels` already exists) — Task 9 only adds a regression test confirming that.

---

## Task 1: Extend QA schemas

**Files:**
- Modify: `src/services/chat/schemas/output.py:290-320`
- Modify: `src/services/chat/schemas/__init__.py:40-43,90-93`
- Test: `src/services/chat/tests/test_qa_schema.py`

- [ ] **Step 1: Write the failing test**

Add to `src/services/chat/tests/test_qa_schema.py`:

```python
def test_qascope_complexity_defaults_simple():
    from src.services.chat.schemas import QAScope
    s = QAScope(target_gap="why bias and variance trade off")
    assert s.complexity == "simple"
    assert s.sub_questions == []

def test_qascope_compound_with_subquestions():
    from src.services.chat.schemas import QAScope
    s = QAScope(target_gap="x", complexity="compound",
               sub_questions=["what is bias", "what is variance"])
    assert s.complexity == "compound"
    assert len(s.sub_questions) == 2

def test_qafinding_shape():
    from src.services.chat.schemas import QAFinding
    f = QAFinding(sub_question="what is bias", text="Bias is …", pertinent=True)
    assert f.sub_question == "what is bias"
    assert f.citations == []
    assert f.pertinent is True

def test_qaanswer_still_lean():
    # Anti-tutor-drift guarantee: QAAnswer has no tutor structural fields.
    from src.services.chat.schemas import QAAnswer
    fields = set(QAAnswer.model_fields)
    assert {"sections", "aspects", "figures"} & fields == set()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'QAFinding'`, and `complexity` attribute missing.

- [ ] **Step 3: Extend `QAScope` and add `QAFinding` in `output.py`**

Replace the `QAScope` class (lines ~290-303) with:

```python
class QAScope(BaseModel):
    """Parsed scope of a punctual question.

    ``target_gap`` is the precise thing to answer; ``assumed_known`` lists what
    the user already understands (so generation must NOT re-explain it);
    ``answer_form`` hints the shape of the reply. ``complexity`` drives the
    adaptive retrieval gate; ``sub_questions`` carry the decomposition for the
    compound path (internal retrieval only — never rendered).
    """

    target_gap: str
    assumed_known: list[str] = Field(default_factory=list)
    answer_form: Literal[
        "explanation", "definition", "comparison",
        "derivation", "yes_no", "list",
    ] = "explanation"
    complexity: Literal["simple", "compound"] = "simple"
    sub_questions: list[str] = Field(default_factory=list)
```

Immediately after the `QAScope` class, add:

```python
class QAFinding(BaseModel):
    """One analyst subagent's grounded mini-finding for a single sub-question.

    Internal to the compound retrieval path — fused by the organizer into the
    lean QAAnswer and then discarded. ``pertinent`` is the analyst's judgement
    of whether its evidence actually serves the CENTRAL question.
    """

    sub_question: str
    text: str = ""
    citations: list[TutorCitation] = Field(default_factory=list)
    pertinent: bool = True
```

(`TutorCitation` and `Literal`/`Field` are already imported in this file.)

- [ ] **Step 4: Re-export `QAFinding` from `__init__.py`**

In `src/services/chat/schemas/__init__.py`, add `QAFinding,` to the import block (after `QAScope,` on line ~40) and `"QAFinding",` to `__all__` (after `"QAScope",` on line ~90).

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_schema.py -v`
Expected: PASS (all four tests).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/schemas/output.py src/services/chat/schemas/__init__.py src/services/chat/tests/test_qa_schema.py
git commit -m "feat(qa): extend QAScope (complexity/sub_questions) + add QAFinding"
```

---

## Task 2: grounded-qa skill + scope prompt

**Files:**
- Create: `src/services/chat/agents/qa_skills/grounded-qa/SKILL.md`
- Modify: `src/services/chat/prompts/qa.py:12-41` (scope prompt) and append agent system prompt
- Test: `src/services/chat/tests/test_qa_prompts.py`

- [ ] **Step 1: Write the failing test**

Create `src/services/chat/tests/test_qa_prompts.py`:

```python
from pathlib import Path

def test_grounded_qa_skill_has_frontmatter():
    p = (Path("src/services/chat/agents/qa_skills/grounded-qa/SKILL.md"))
    text = p.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: grounded-qa" in text
    # anti-tutor-drift rule must be present
    assert "no recommendations" in text.lower() or "no tutor" in text.lower()

def test_scope_prompt_mentions_complexity():
    from src.services.chat.prompts.qa import QA_SCOPE_PROMPT
    assert "complexity" in QA_SCOPE_PROMPT
    assert "sub_questions" in QA_SCOPE_PROMPT

def test_agent_system_prompt_exists():
    from src.services.chat.prompts.qa import QA_AGENT_PROMPT
    assert "grounded-qa" in QA_AGENT_PROMPT
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_prompts.py -v`
Expected: FAIL — file not found / `QA_AGENT_PROMPT` import error.

- [ ] **Step 3: Create the skill file**

Create `src/services/chat/agents/qa_skills/grounded-qa/SKILL.md`:

```markdown
---
name: grounded-qa
description: Answer ONE scoped question from textbook sources — bounded agentic retrieval, pertinence to the central question, cite every claim, no tutor-style scaffolding.
---

# Grounded Q&A skill

## When to use
When answering a single punctual question grounded in retrieved textbook
sources. Sources accumulate as files under `/sources/`.

## Instructions
1. Call `search_corpus` with a focused query for the `target_gap`. Read the
   returned briefs and the `/sources/*.md` files.
2. Coverage check: is `target_gap` actually answerable from the evidence? If
   not, refine the query and call `search_corpus` again. Stop after at most the
   allowed number of rounds (you will be told the cap).
3. Pertinence: keep only evidence that serves the CENTRAL `target_gap`. Discard
   tangents even if individually interesting.
4. Skip everything in `assumed_known` — do not define, explain, or re-derive it.
5. Write ONLY the answer to `target_gap`. PUNCTUAL:
   - NO recommendations, NO "intuition" asides, NO worked examples, NO
     multi-section structure, NO "in summary" — UNLESS `answer_form` is
     explicitly `list`/`derivation` (then give exactly that shape).
   - This is NOT a tutor answer. Do not teach the broader topic.
6. Cite every factual claim with inline `[n]` markers tied to the `/sources/`
   files you used.
7. Honesty: if the corpus does not cover `target_gap`, say so in one sentence
   and emit zero citations. Never fabricate a source.

## Output
Emit the `QAAnswer` structured object: terse `text` (markdown, `[n]` markers),
`citations` (one per marker), `math_blocks` (LaTeX display equations, may be
empty). Echo the given `scope`.
```

- [ ] **Step 4: Update scope prompt + add agent prompt in `prompts/qa.py`**

In `QA_SCOPE_PROMPT`, replace the `<output_format>` block's key list to add the two new keys, and extend the example. Set the output_format keys to:

```
  "target_gap": string — the single specific thing the student wants answered.
  "assumed_known": array of strings — concepts the student SIGNALS they already
      understand. Empty array if none signalled.
  "answer_form": one of "explanation","definition","comparison","derivation",
      "yes_no","list" — the natural shape of the answer.
  "complexity": "simple" or "compound" — "compound" ONLY when the question has
      two or more distinct facets that each need their own retrieval; otherwise
      "simple".
  "sub_questions": array of strings — present (2-4 focused, self-contained
      retrieval queries) ONLY when complexity is "compound"; [] when "simple".
```

Update the example output to:

```
{"target_gap":"why bias and variance trade off against each other",
"assumed_known":["what bias is","what variance is"],
"answer_form":"explanation","complexity":"simple","sub_questions":[]}
```

Add a `<rules>` line:

```
- Prefer "simple". Use "compound" only for genuinely multi-facet questions.
```

Then append a new constant at the end of `prompts/qa.py`:

```python
QA_AGENT_PROMPT = """<role>
You answer ONE specific question, grounded ONLY in retrieved textbook sources.
</role>

<task>
Use the grounded-qa skill. Call search_corpus to gather evidence into /sources/,
self-check coverage of target_gap, then emit the QAAnswer.
</task>

<rules>
- Answer ONLY target_gap. Skip everything in assumed_known.
- PUNCTUAL: no recommendations, examples, intuition asides, or multi-section
  structure unless answer_form demands it. This is NOT a tutor answer.
- Cite every claim with [n] markers tied to /sources/.
- If the corpus does not cover it, say so in one sentence, no citations.
</rules>
"""

QA_ANALYST_PROMPT = """<role>
You research ONE sub-question and report a grounded finding.
</role>

<task>
Call search_corpus for your sub-question, read /sources/, and return a QAFinding:
the sub_question, a terse grounded text with [n] markers, its citations, and
`pertinent` = whether your evidence actually serves the CENTRAL question
(provided in the prompt).
</task>

<rules>
- Keep only evidence pertinent to the CENTRAL question; set pertinent=false if
  your sub-question turned out off-target.
- Ground every claim; never invent sources.
</rules>
"""
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_prompts.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/qa_skills/grounded-qa/SKILL.md src/services/chat/prompts/qa.py src/services/chat/tests/test_qa_prompts.py
git commit -m "feat(qa): grounded-qa skill + scope-prompt complexity + agent/analyst prompts"
```

---

## Task 3: `search_corpus` tool + StoreBackend `/sources/`

**Files:**
- Modify: `src/services/chat/agents/qa.py` (add tool factory + store builder)
- Test: `src/services/chat/tests/test_qa_tool.py`

The tool is a closure over `book_slugs` + a shared dict of accumulated sources (so `run_qa` can read them back for `sources_full`). It writes each hit to the store's `/sources/<n>.md` and returns a compact brief string.

- [ ] **Step 1: Write the failing test**

Create `src/services/chat/tests/test_qa_tool.py`:

```python
from src.services.chat.schemas import Source

def _src(i, cid):
    return Source(rank=i, book="hansen", book_name="Hansen", authors_short="Hansen",
                  year=2022, chapter="ch07", section="7.1", title="Bias",
                  excerpt="ex", chunk="Bias is systematic error.", score=0.9, chunkId=cid)

def test_search_corpus_accumulates_and_dedups(monkeypatch):
    import src.services.chat.agents.qa as qa
    calls = {"n": 0}
    def fake_hybrid(query, **kw):
        calls["n"] += 1
        return ([_src(1, "c1"), _src(2, "c2")], {"collections": ["x"]})
    monkeypatch.setattr(qa, "hybrid_search", fake_hybrid)

    acc = {}
    tool = qa._make_search_corpus(book_slugs=["hansen"], acc=acc, k=4)
    out1 = tool.invoke({"query": "what is bias"})
    assert "Bias" in out1 and "[1]" in out1
    assert set(acc.keys()) == {"c1", "c2"}
    # second call with an overlapping hit does not duplicate
    tool.invoke({"query": "bias again"})
    assert set(acc.keys()) == {"c1", "c2"}  # same chunkIds → deduped
    assert calls["n"] == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_tool.py -v`
Expected: FAIL — `_make_search_corpus` not defined.

- [ ] **Step 3: Implement the tool factory in `qa.py`**

Add near the top of `qa.py` (keep existing imports; add `from langchain.tools import tool`):

```python
def _brief_line(n: int, s: Source) -> str:
    body = (s.chunk or s.excerpt or "")[:_CHUNK_PREVIEW_CHARS]
    return (f"[{n}] {s.book_name or s.book} · {s.chapter} {s.section} — "
            f"{s.title}\n{body}")


def _make_search_corpus(*, book_slugs: list[str] | None, acc: dict, k: int):
    """Build the search_corpus LangChain tool.

    Closure over ``acc`` (chunkId -> Source) so run_qa can recover the full
    source list afterwards. Dedups by chunkId across rounds. Returns a compact
    numbered brief over the *newly added* hits.
    """
    from langchain.tools import tool as _tool

    @_tool
    def search_corpus(query: str) -> str:
        """Search the selected textbooks for passages relevant to `query`.
        Returns numbered source briefs. Call again with a refined query if the
        target gap is not yet covered."""
        sources, _meta = hybrid_search(
            query, book_slugs=book_slugs, top_k=max(1, k),
            rerank=True, rerank_top_n=max(1, k), adjacent_sections=False)
        lines = []
        for s in sources:
            if s.chunkId in acc:
                continue
            acc[s.chunkId] = s
            lines.append(_brief_line(len(acc), s))
        if not lines:
            return "No new passages found for that query."
        return "\n\n".join(lines)

    return search_corpus
```

(`hybrid_search`, `Source`, `_CHUNK_PREVIEW_CHARS` already imported/defined in `qa.py`.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_tool.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/tests/test_qa_tool.py
git commit -m "feat(qa): search_corpus tool with dedup accumulator"
```

---

## Task 4: Scope pre-pass emits complexity + sub-questions

**Files:**
- Modify: `src/services/chat/agents/qa.py` (`extract_scope`)
- Test: `src/services/chat/tests/test_qa_scope.py`

- [ ] **Step 1: Write the failing test**

Create `src/services/chat/tests/test_qa_scope.py`:

```python
import json
import pytest

@pytest.mark.asyncio
async def test_extract_scope_parses_compound(monkeypatch):
    import src.services.chat.agents.qa as qa
    async def fake_chat(messages, **kw):
        return json.dumps({
            "target_gap": "how X relates to Y",
            "assumed_known": [], "answer_form": "explanation",
            "complexity": "compound",
            "sub_questions": ["what is X", "what is Y"],
        })
    monkeypatch.setattr(qa, "_chat", fake_chat)
    scope = await qa.extract_scope("what are X and Y and how do they relate?")
    assert scope.complexity == "compound"
    assert scope.sub_questions == ["what is X", "what is Y"]

@pytest.mark.asyncio
async def test_extract_scope_failopen_simple(monkeypatch):
    import src.services.chat.agents.qa as qa
    async def boom(messages, **kw):
        raise RuntimeError("provider down")
    monkeypatch.setattr(qa, "_chat", boom)
    scope = await qa.extract_scope("why bias and variance trade off")
    assert scope.complexity == "simple"
    assert scope.sub_questions == []
    assert scope.target_gap == "why bias and variance trade off"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_scope.py -v`
Expected: FAIL — `extract_scope` ignores `complexity`/`sub_questions`.

- [ ] **Step 3: Update `extract_scope` in `qa.py`**

In `extract_scope`, change the `fallback` and the success-path `QAScope(...)` build to include the new fields:

```python
    fallback = QAScope(target_gap=query.strip(), assumed_known=[],
                       answer_form="explanation", complexity="simple",
                       sub_questions=[])
```

and in the `try` block after `data = json.loads(...)`:

```python
        complexity = data.get("complexity") if data.get("complexity") in {"simple", "compound"} else "simple"
        subs = [str(x).strip() for x in (data.get("sub_questions") or []) if str(x).strip()]
        if complexity != "compound":
            subs = []
        return QAScope(
            target_gap=str(data.get("target_gap") or query).strip(),
            assumed_known=[str(x).strip() for x in (data.get("assumed_known") or []) if str(x).strip()],
            answer_form=data.get("answer_form") if data.get("answer_form") in {
                "explanation", "definition", "comparison", "derivation", "yes_no", "list"
            } else "explanation",
            complexity=complexity,
            sub_questions=subs,
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_scope.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/tests/test_qa_scope.py
git commit -m "feat(qa): scope pre-pass emits complexity + sub_questions (fail-open simple)"
```

---

## Task 5: Simple-path deepagent (build + run)

**Files:**
- Modify: `src/services/chat/agents/qa.py` (add `_build_simple_agent`, `_run_agent_structured`, `answer_simple`)
- Test: `src/services/chat/tests/test_qa_simple.py`

Pattern mirrors `ow_deepagents.synthesize_structured` but standalone (NO tutor imports). Tests monkeypatch `qa.create_deep_agent`.

- [ ] **Step 1: Write the failing test**

Create `src/services/chat/tests/test_qa_simple.py`:

```python
import pytest
from src.services.chat.schemas import QAScope, QAAnswer, Source

def _src(cid):
    return Source(rank=1, book="hansen", book_name="Hansen", authors_short="Hansen",
                  year=2022, chapter="ch07", section="7.1", title="Bias",
                  excerpt="ex", chunk="Bias is systematic error.", score=0.9, chunkId=cid)

class _FakeAgent:
    def __init__(self, answer): self._answer = answer
    def invoke(self, inp, config):
        return {"structured_response": self._answer}

@pytest.mark.asyncio
async def test_answer_simple_returns_qaanswer(monkeypatch):
    import src.services.chat.agents.qa as qa
    scope = QAScope(target_gap="why bias and variance trade off")
    expected = QAAnswer(text="Because reducing one raises the other [1].",
                        scope=scope)
    monkeypatch.setattr(qa, "create_deep_agent",
                        lambda **kw: _FakeAgent(expected), raising=False)
    acc = {"c1": _src("c1")}
    ans = await qa.answer_simple(scope, book_slugs=["hansen"], acc=acc)
    assert isinstance(ans, QAAnswer)
    assert "trade" in ans.text or "[1]" in ans.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_simple.py -v`
Expected: FAIL — `answer_simple` / `create_deep_agent` not defined.

- [ ] **Step 3: Implement in `qa.py`**

Add these helpers (top-level). Keep `create_deep_agent = None` as a module attribute so tests can monkeypatch it and prod lazy-imports the real one:

```python
import asyncio

create_deep_agent = None  # monkeypatch seam; real one lazy-imported in _cda()

_QA_MAX_ROUNDS = int(os.environ.get("QA_MAX_ROUNDS", "3"))


def _cda():
    """Resolve create_deep_agent: monkeypatched module attr wins, else import."""
    if create_deep_agent is not None:
        return create_deep_agent
    from deepagents import create_deep_agent as _real  # noqa: PLC0415
    return _real


def _qa_skill_dir() -> str:
    import os as _os
    return _os.path.join(_os.path.dirname(__file__), "qa_skills")


def _store_with_skill():
    """InMemoryStore preloaded with the grounded-qa skill."""
    from deepagents.backends.utils import create_file_data
    from langgraph.store.memory import InMemoryStore
    from pathlib import Path
    store = InMemoryStore()
    skill = (Path(_qa_skill_dir()) / "grounded-qa" / "SKILL.md").read_text(encoding="utf-8")
    store.put(namespace=("filesystem",), key="/skills/grounded-qa/SKILL.md",
              value=create_file_data(skill))
    return store


def _lc_model(model: str | None):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model or settings.openai_model_nano, temperature=0.0,
                      api_key=settings.openai_api_key)


async def _run_structured(agent, user_content: str):
    """Invoke a deep agent in a thread; return its structured_response or None."""
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user", "content": user_content}]},
        {"configurable": {"thread_id": "qa"}})
    return result.get("structured_response") if isinstance(result, dict) else None


async def answer_simple(scope: QAScope, *, book_slugs: list[str] | None,
                        acc: dict, model: str | None = None) -> QAAnswer:
    """Single bounded-retrieval deepagent → QAAnswer."""
    from deepagents.backends import StoreBackend
    from langchain.agents.structured_output import ToolStrategy
    from src.services.chat.prompts.qa import QA_AGENT_PROMPT

    store = _store_with_skill()
    search = _make_search_corpus(book_slugs=book_slugs, acc=acc, k=_QA_TOP_K)
    agent = _cda()(
        model=_lc_model(model), tools=[search],
        system_prompt=QA_AGENT_PROMPT,
        backend=lambda rt: StoreBackend(rt), store=store, skills=["/skills/"],
        response_format=ToolStrategy(QAAnswer, handle_errors=True))
    user = (
        f"Central question (target_gap): {scope.target_gap}\n"
        f"assumed_known: {json.dumps(scope.assumed_known)}\n"
        f"answer_form: {scope.answer_form}\n"
        f"Retrieval cap: {_QA_MAX_ROUNDS} search_corpus calls.\n"
        "Gather evidence with search_corpus, then emit the QAAnswer.")
    ans = await _run_structured(agent, user)
    if isinstance(ans, QAAnswer):
        return ans.model_copy(update={"scope": scope})
    raise RuntimeError("simple agent returned no structured QAAnswer")
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_simple.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/tests/test_qa_simple.py
git commit -m "feat(qa): simple-path deepagent (search_corpus loop → QAAnswer)"
```

---

## Task 6: Compound-path subagents (build + organize)

**Files:**
- Modify: `src/services/chat/agents/qa.py` (add `answer_compound`)
- Test: `src/services/chat/tests/test_qa_compound.py`

One analyst subagent per sub-question (each `response_format=QAFinding`, own `search_corpus` tool, `grounded-qa` skill). Main agent organizes into a lean `QAAnswer`.

- [ ] **Step 1: Write the failing test**

Create `src/services/chat/tests/test_qa_compound.py`:

```python
import pytest
from src.services.chat.schemas import QAScope, QAAnswer

class _FakeAgent:
    def __init__(self, answer): self._answer = answer
    def invoke(self, inp, config):
        return {"structured_response": self._answer}

@pytest.mark.asyncio
async def test_answer_compound_emits_lean_qaanswer(monkeypatch):
    import src.services.chat.agents.qa as qa
    scope = QAScope(target_gap="how X and Y relate", complexity="compound",
                    sub_questions=["what is X", "what is Y"])
    captured = {}
    def fake_cda(**kw):
        captured["subagents"] = kw.get("subagents")
        return _FakeAgent(QAAnswer(text="X and Y relate via Z [1].", scope=scope))
    monkeypatch.setattr(qa, "create_deep_agent", fake_cda, raising=False)
    acc = {}
    ans = await qa.answer_compound(scope, book_slugs=["hansen"], acc=acc)
    assert isinstance(ans, QAAnswer)
    # one analyst subagent per sub-question
    assert len(captured["subagents"]) == 2
    # lean: no tutor fields leak in
    assert set(ans.model_dump()) >= {"text", "scope", "citations"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_compound.py -v`
Expected: FAIL — `answer_compound` not defined.

- [ ] **Step 3: Implement `answer_compound` in `qa.py`**

```python
def _sub_slug(i: int) -> str:
    return f"analyst-{i + 1}"


async def answer_compound(scope: QAScope, *, book_slugs: list[str] | None,
                          acc: dict, model: str | None = None,
                          analyst_model: str | None = None) -> QAAnswer:
    """Decompose → one analyst subagent per sub-question → organize → QAAnswer."""
    from deepagents.backends import StoreBackend
    from langchain.agents.structured_output import ToolStrategy
    from src.services.chat.prompts.qa import QA_AGENT_PROMPT, QA_ANALYST_PROMPT
    from src.services.chat.schemas import QAFinding

    store = _store_with_skill()
    search = _make_search_corpus(book_slugs=book_slugs, acc=acc, k=_QA_TOP_K)

    subagents = [{
        "name": _sub_slug(i),
        "description": f"Research sub-question and report a grounded QAFinding: {sq}",
        "system_prompt": (QA_ANALYST_PROMPT
                          + f"\n\nCENTRAL question: {scope.target_gap}"
                          + f"\nYOUR sub-question: {sq}"),
        "tools": [search],
        "skills": ["/skills/"],
        "response_format": QAFinding,
    } for i, sq in enumerate(scope.sub_questions)]

    sub_list = "; ".join(f"{_sub_slug(i)} → {sq}" for i, sq in enumerate(scope.sub_questions))
    agent = _cda()(
        model=_lc_model(model), tools=[search], subagents=subagents,
        system_prompt=(QA_AGENT_PROMPT
                       + "\n\nDelegate each sub-question to its analyst subagent "
                         "via the task tool, then FUSE the findings into ONE lean "
                         "answer to the CENTRAL question. Drop non-pertinent "
                         "findings. Do not list the sub-questions in the answer."),
        backend=lambda rt: StoreBackend(rt), store=store, skills=["/skills/"],
        response_format=ToolStrategy(QAAnswer, handle_errors=True))
    user = (
        f"Central question (target_gap): {scope.target_gap}\n"
        f"assumed_known: {json.dumps(scope.assumed_known)}\n"
        f"answer_form: {scope.answer_form}\n"
        f"Sub-questions and their analysts: {sub_list}\n"
        "Delegate, then emit the fused QAAnswer.")
    ans = await _run_structured(agent, user)
    if isinstance(ans, QAAnswer):
        return ans.model_copy(update={"scope": scope})
    raise RuntimeError("compound agent returned no structured QAAnswer")
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_compound.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/tests/test_qa_compound.py
git commit -m "feat(qa): compound-path analyst subagents → fused lean QAAnswer"
```

---

## Task 7: Orchestration — gate, fallback, run_qa rewrite

**Files:**
- Modify: `src/services/chat/agents/qa.py` (`run_qa`, add `_fallback_answer`)
- Test: `src/services/chat/tests/test_qa_run.py` (extend), `src/services/chat/tests/test_qa_fallback.py`

`run_qa` keeps the existing pre-amble (meta, book resolve, clarify, scope) and the corpus-miss/verify/SSE tail, but replaces the single `generate_scoped` call with: gate on `scope.complexity` → `answer_simple`/`answer_compound`, wrapped in a fallback to the legacy deterministic path on any agent failure. Progress events are emitted before the agent runs.

- [ ] **Step 1: Write the failing tests**

Create `src/services/chat/tests/test_qa_fallback.py`:

```python
import pytest
from src.services.chat.schemas import ChatRequest, QAScope, Source

def _src(cid):
    return Source(rank=1, book="hansen", book_name="Hansen", authors_short="H",
                  year=2022, chapter="ch07", section="7.1", title="Bias",
                  excerpt="ex", chunk="Bias is systematic error.", score=0.9, chunkId=cid)

@pytest.mark.asyncio
async def test_run_qa_falls_back_on_agent_error(monkeypatch):
    import src.services.chat.agents.qa as qa
    # scope → simple
    async def fake_scope(q, **kw):
        return QAScope(target_gap=q, complexity="simple")
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    # book resolve no-op
    async def fake_resolve(*a, **k):
        from src.services.chat.agents._scope import BookResolution
        return BookResolution(book_slug="hansen", candidates=[], confidence=1.0, reason="")
    monkeypatch.setattr(qa, "resolve_book", fake_resolve)
    monkeypatch.setattr(qa, "maybe_clarify", lambda *a, **k: None)
    monkeypatch.setattr(qa, "parse_catalog", lambda: [])
    monkeypatch.setattr(qa, "hybrid_search",
                        lambda q, **kw: ([_src("c1")], {"collections": []}))
    # agent path explodes → must fall back, not crash
    async def boom(*a, **k): raise RuntimeError("deepagents down")
    monkeypatch.setattr(qa, "answer_simple", boom)
    # legacy generate used by fallback
    async def fake_gen(scope, sources, **kw):
        from src.services.chat.schemas import QAAnswer
        return QAAnswer(text="fallback answer [1]", scope=scope)
    monkeypatch.setattr(qa, "generate_scoped", fake_gen)
    monkeypatch.setattr(qa, "_QA_VERIFY", False)

    req = ChatRequest(message="why bias trades off", mode="qa", bookFilter=["hansen"])
    events = [e async for e in qa.run_qa(req)]
    kinds = [e["type"] for e in events]
    assert "structured_output" in kinds
    assert kinds[-1] == "done"
    so = next(e for e in events if e["type"] == "structured_output")
    assert "fallback" in so["data"]["text"]
```

(Adjust the `BookResolution` import to the real class/fields in `agents/_scope.py` if they differ.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_fallback.py -v`
Expected: FAIL — `run_qa` still calls `generate_scoped` directly (no gate/fallback wiring) or `_fallback_answer` missing.

- [ ] **Step 3: Add `_fallback_answer` and rewire `run_qa`**

Add the fallback helper (reuses the existing `generate_scoped` + `verify_grounding`):

```python
async def _fallback_answer(scope: QAScope, sources: list[Source],
                           req: ChatRequest) -> QAAnswer:
    """Legacy deterministic path: single hybrid retrieval already done →
    generate_scoped (+verify). Used when the deepagent path fails so Q&A never
    regresses below the prior behaviour."""
    answer = await generate_scoped(scope, sources, model=_model_for("generate", req))
    if _QA_VERIFY:
        answer = await verify_grounding(answer, sources, model=_model_for("verify", req))
    elif not answer.grounding:
        answer = answer.model_copy(update={
            "grounding": {"ok": True, "unsupported": [], "confidence": 0.7}})
    return answer
```

In `run_qa`, replace the `try:`/generate/verify block (current lines ~315-328) with the gated agent path + fallback. Keep the corpus-miss block above it unchanged:

```python
    acc: dict = {s.chunkId: s for s in sources}
    try:
        if scope.complexity == "compound" and _QA_DECOMPOSE and scope.sub_questions:
            yield {"type": "progress", "stage": "analyzing",
                   "subQuestions": scope.sub_questions}
            answer = await answer_compound(
                scope, book_slugs=book_slugs, acc=acc,
                model=_model_for("agent", req),
                analyst_model=_model_for("analyst", req))
        else:
            yield {"type": "progress", "stage": "retrieving", "round": 1}
            answer = await answer_simple(
                scope, book_slugs=book_slugs, acc=acc,
                model=_model_for("agent", req))
        # verify post-pass (advisory) on the agent answer
        if _QA_VERIFY:
            answer = await verify_grounding(answer, list(acc.values()),
                                            model=_model_for("verify", req))
    except Exception:  # noqa: BLE001
        logger.exception("qa agent path failed; deterministic fallback")
        try:
            answer = await _fallback_answer(scope, sources, req)
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "code": type(exc).__name__, "message": str(exc)}
            yield {"type": "done"}
            return
    sources = list(acc.values())  # agent may have retrieved more rounds
```

Add the env flag near the other QA flags at the top of `qa.py`:

```python
_QA_DECOMPOSE = os.environ.get("QA_DECOMPOSE", "1") == "1"
```

The existing tail (`structured_output` → `sources_full` → `retrieval_meta` → `usage` → `done`) stays; it now renders the accumulated `sources`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_fallback.py src/services/chat/tests/test_qa_run.py -v`
Expected: PASS. Fix any `test_qa_run.py` assertions that assumed the old single-generate path (e.g. monkeypatching `generate_scoped`) by pointing them at `answer_simple` or asserting the new `progress` event.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/qa.py src/services/chat/tests/test_qa_fallback.py src/services/chat/tests/test_qa_run.py
git commit -m "feat(qa): gate simple/compound + deterministic fallback + progress events"
```

---

## Task 8: `_model_for` stage keys + full backend suite green

**Files:**
- Modify: `src/services/chat/agents/qa.py` (`_model_for` already generic; add env names)
- Test: run the whole QA suite

`_model_for(stage, req)` already reads `stageModels[stage]` then `QA_<STAGE>_MODEL`. New stages `"agent"` and `"analyst"` work automatically. This task just confirms the suite is green and adds a registry regression test.

- [ ] **Step 1: Write the failing test**

Create `src/services/chat/tests/test_qa_stage_models.py`:

```python
def test_model_for_agent_stage_env(monkeypatch):
    import src.services.chat.agents.qa as qa
    from src.services.chat.schemas import ChatRequest
    monkeypatch.setenv("QA_AGENT_MODEL", "deepseek-chat")
    req = ChatRequest(message="x", mode="qa")
    assert qa._model_for("agent", req) == "deepseek-chat"

def test_model_for_stagemodels_override():
    import src.services.chat.agents.qa as qa
    from src.services.chat.schemas import ChatRequest
    req = ChatRequest(message="x", mode="qa", stageModels={"analyst": "gpt-4o"})
    assert qa._model_for("analyst", req) == "gpt-4o"
```

- [ ] **Step 2: Run to verify it fails / passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_qa_stage_models.py -v`
Expected: PASS already (generic resolver) — if FAIL, ensure `_model_for` uppercases the stage for the env name (`QA_{stage.upper()}_MODEL`), which it does. Keep the test as a regression guard.

- [ ] **Step 3: Run the whole QA + routing suite**

Run:
```
.venv/bin/python -m pytest src/services/chat/tests/ -k "qa or mode_routing or mode_parity" -v
```
Expected: PASS. Fix any stragglers (old `test_qa_nodes.py`/`test_qa_clarify.py` referencing removed internals — update them to the new helpers; do not delete coverage).

- [ ] **Step 4: Commit**

```bash
git add src/services/chat/tests/test_qa_stage_models.py
git commit -m "test(qa): stage-model resolution for agent/analyst stages"
```

---

## Task 9: Frontend — types, pipeline diagram, card, thread

**Files:**
- Modify: `web/src/types.ts`
- Modify: `web/src/data/qaPipeline.ts`
- Modify: `web/src/components/QAPipelineDiagram.tsx`
- Modify: `web/src/components/QAAnswerCard.tsx`
- Modify: `web/src/components/MessageThread.tsx`
- Test: `web/src/data/qaPipeline.test.ts`, `web/src/components/QAPipelineDiagram.test.tsx`, `web/src/types.qa.test.ts`

- [ ] **Step 1: Write the failing test**

Add to `web/src/types.qa.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import type { QAScope, QAFinding } from "./types";

describe("QA types", () => {
  it("QAScope has complexity + sub_questions", () => {
    const s: QAScope = {
      target_gap: "x", assumed_known: [], answer_form: "explanation",
      complexity: "compound", sub_questions: ["a", "b"],
    };
    expect(s.complexity).toBe("compound");
    expect(s.sub_questions.length).toBe(2);
  });
  it("QAFinding shape", () => {
    const f: QAFinding = { sub_question: "a", text: "t", citations: [], pertinent: true };
    expect(f.pertinent).toBe(true);
  });
});
```

Add to `web/src/data/qaPipeline.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { QA_PIPELINE } from "./qaPipeline";

describe("QA pipeline graph", () => {
  it("has the new agentic node ids", () => {
    const ids = QA_PIPELINE.nodes.map(n => n.id);
    for (const id of ["scope", "gate", "simple", "compound", "organize", "verify"]) {
      expect(ids).toContain(id);
    }
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/types.qa.test.ts src/data/qaPipeline.test.ts`
Expected: FAIL — `complexity`/`QAFinding` missing; node ids absent.

- [ ] **Step 3: Update `types.ts`**

In `web/src/types.ts`, extend `QAScope` and add `QAFinding`:

```typescript
export interface QAScope {
  target_gap: string;
  assumed_known: string[];
  answer_form: "explanation" | "definition" | "comparison" | "derivation" | "yes_no" | "list";
  complexity: "simple" | "compound";
  sub_questions: string[];
}

export interface QAFinding {
  sub_question: string;
  text: string;
  citations: TutorCitation[];
  pertinent: boolean;
}
```

(`QAAnswer` interface unchanged. `TutorCitation` already imported/defined.)

- [ ] **Step 4: Reshape `qaPipeline.ts`**

Replace the `QANode["id"]` union and `QA_PIPELINE` nodes/edges with the agentic shape:

```typescript
export interface QANode {
  id: "scope" | "gate" | "simple" | "compound" | "organize" | "verify" | "clarify";
  label: string;
  desc: string;
  kind: "llm" | "data";
  defaultModel: string;
}
```

Nodes (keep `defaultModel: "gpt-5.4-nano-2026-03-17"` for llm nodes):

```typescript
export const QA_PIPELINE: { nodes: QANode[]; edges: QAEdge[] } = {
  nodes: [
    { id: "scope", label: "Scope + resolve book", kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
      desc: "Parses your question into {target gap, what you already know, answer form} and classifies simple vs compound. Fuzzy-resolves the named book against the catalog." },
    { id: "gate", label: "Complexity gate", kind: "data", defaultModel: "—",
      desc: "Routes simple questions to a single bounded retrieval loop; compound questions to per-sub-question analyst subagents." },
    { id: "simple", label: "Agentic retrieval (simple)", kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
      desc: "A deepagent calls search_corpus up to 3× over the selected books, self-checks coverage, re-queries on miss, then writes the scoped answer. Evidence offloaded to /sources/." },
    { id: "compound", label: "Analyst subagents (compound)", kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
      desc: "One analyst subagent per sub-question retrieves and pertinence-filters its own hits in isolated context, returning a grounded finding." },
    { id: "organize", label: "Organize", kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
      desc: "Fuses the findings into ONE lean answer to the central question — no tutor-style scaffolding. Drops non-pertinent findings." },
    { id: "verify", label: "Grounding verify", kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
      desc: "Audits each claim against /sources/; softens unsupported ones and sets the grounding badge. Advisory — never blocks." },
    { id: "clarify", label: "Clarify (if ambiguous)", kind: "data", defaultModel: "—",
      desc: "If the named book is unknown/ambiguous the run stops and asks you to pick. A confident match skips this." },
  ],
  edges: [
    { from: "scope", to: "clarify" },
    { from: "scope", to: "gate" },
    { from: "gate", to: "simple" },
    { from: "gate", to: "compound" },
    { from: "simple", to: "organize" },
    { from: "compound", to: "organize" },
    { from: "organize", to: "verify" },
  ],
};
```

- [ ] **Step 5: Update `QAPipelineDiagram.tsx`**

If the diagram renders nodes from `QA_PIPELINE` dynamically, no logic change is needed — only confirm the per-stage dropdown shows for the new `llm` nodes (`simple`/`compound`/`organize`) and the fixed label for `gate`/`clarify`. If node ids are hardcoded anywhere (the `pipe2__model-fixed` test id maps positionally), update those references to the new node order. Adjust `QAPipelineDiagram.test.tsx` `data-testid` expectations to the new node ids accordingly.

- [ ] **Step 6: Optional complexity hint in `QAAnswerCard.tsx`**

Below the scope line, when `answer.scope.complexity === "compound"`, render a muted hint:

```tsx
{answer.scope.complexity === "compound" && answer.scope.sub_questions.length > 0 && (
  <p className="qa-card__subhint">
    Answered via {answer.scope.sub_questions.length} sub-questions
  </p>
)}
```

- [ ] **Step 7: Progress events in `MessageThread.tsx`**

Where SSE events are consumed, handle `type === "progress"`: show a transient status line (`stage === "retrieving"` → "Retrieving…"; `stage === "analyzing"` → `Analyzing ${subQuestions.length} sub-questions…`). It is cleared when `structured_output` arrives. Keep the existing `schema === "QAAnswer"` → `<QAAnswerCard>` branch unchanged.

- [ ] **Step 8: Run frontend tests**

Run: `cd web && npx vitest run src/types.qa.test.ts src/data/qaPipeline.test.ts src/components/QAPipelineDiagram.test.tsx src/components/QAAnswerCard.test.tsx`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add web/src/types.ts web/src/data/qaPipeline.ts web/src/components/QAPipelineDiagram.tsx web/src/components/QAAnswerCard.tsx web/src/components/MessageThread.tsx web/src/types.qa.test.ts web/src/data/qaPipeline.test.ts
git commit -m "feat(qa-web): agentic pipeline diagram, QAFinding type, progress events"
```

---

## Task 10: Docs lockstep + browser verify

**Files:**
- Modify: `docs/services/chat-features/51-qa-mode.md` (rewrite)
- Modify: `docs/system/invariants.md`, `docs/system/changelog.md`, `docs/services/chat.md`

- [ ] **Step 1: Rewrite `51-qa-mode.md`**

Replace the "Pipeline — four nodes" section with the agentic architecture (scope → gate → simple/compound → organize → verify), update the mermaid graph to match `qaPipeline.ts` edges, replace the env-flag table with §8 of the spec (`QA_MAX_ROUNDS`, `QA_DECOMPOSE`, `QA_AGENT_MODEL`, `QA_ANALYST_MODEL` added), add a "Deepagents features used" subsection (copy §3 of the spec), add the "Isolation from tutor" note (copy §2.1), and update the SSE section to include the `progress` events. Update the synced-artifacts checklist to the new file set (skill dir, `qa_skills/grounded-qa`, new tests).

- [ ] **Step 2: Add a changelog entry**

Append to `docs/system/changelog.md` a dated entry: "Q&A rebuilt as scoped agentic-retrieval deepagent (adaptive simple/compound gate, search_corpus tool, grounded-qa skill, deterministic fallback). No tutor files touched." Reference the spec + this plan.

- [ ] **Step 3: Add/extend an invariant**

In `docs/system/invariants.md`, add an invariant: "Q&A emits only `QAAnswer` (no sections/aspects/figures) and never imports tutor modules (`deep_tutor`, `orchestrator_workers`, `ow_deepagents`, tutor prompts, `ow_skills/synthesis`)." Add a grep check: `grep -rn "deep_tutor\|orchestrator_workers\|ow_deepagents\|ow_skills" src/services/chat/agents/qa.py` must return nothing.

- [ ] **Step 4: Run the isolation grep (verify invariant)**

Run: `grep -rn "deep_tutor\|orchestrator_workers\|ow_deepagents\|ow_skills" src/services/chat/agents/qa.py src/services/chat/prompts/qa.py`
Expected: no output (exit 1).

- [ ] **Step 5: Update `docs/services/chat.md`**

Update the Q&A row/section to describe the agentic pipeline in one or two sentences and point to `51-qa-mode.md`.

- [ ] **Step 6: Full suite + browser verify**

Run backend: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Run frontend: `cd web && npx vitest run`
Expected: all green.

Then start `./scripts/dev.sh`, open `http://localhost:5175`, select Q&A, scope a book (e.g. Hansen), and ask:
1. A simple question ("why do bias and variance trade off?") → terse cited answer, no tutor scaffolding.
2. A compound question ("what are bias and variance and how do they trade off?") → still one lean answer; card shows "Answered via N sub-questions".
Open the Q&A `(i)` modal → confirm the new node graph renders and matches `docs/common ground/Elements/index.html`.

- [ ] **Step 7: Commit**

```bash
git add docs/
git commit -m "docs(qa): lockstep — rewrite feature 51, changelog, invariant, chat.md for agentic Q&A"
```

---

## Self-Review notes

- **Spec coverage:** scope+gate (T4/T7), search_corpus tool + /sources/ (T3), simple path (T5), compound subagents (T6), grounded-qa skill (T2), QAFinding + lean QAAnswer (T1), models/stageModels (T8), SSE+progress (T7/T9), error fallback (T7), frontend (T9), docs+isolation invariant (T10). All spec §§ mapped.
- **Isolation:** T10 step 4 grep enforces no tutor imports; no task edits any tutor file.
- **Fallback:** T7 guarantees no regression below current behaviour if deepagents fails.
- **Test seam:** every deepagent task monkeypatches `qa.create_deep_agent` (module attr default `None`) — no live LLM calls in unit tests, matching the `ow_deepagents` test pattern.
