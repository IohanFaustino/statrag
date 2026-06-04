# Deep-agent Structured Synthesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the lossy free-text→`_schema_fill` synthesis with a deep agent that emits a typed `DeepTutorAnswer` directly (`response_format`), enforce component-defining formulas + clean `$…$` math via an enriched skill, build two variants (A: structured synth, B: subagent merge), eval A/B vs current (C) with a few calls, and wire the winner.

**Architecture:** Two new synthesizer functions in `ow_deepagents.py` using `create_deep_agent(..., response_format=ToolStrategy(DeepTutorAnswer, handle_errors=True))`. New harness levels 6 (A) / 7 (B) branch in `run_orchestrator_workers`, returning the structured answer with NO `_schema_fill`. A lightweight 3-arm eval picks the winner; the winner becomes the `orchestrator-deep` default.

**Tech Stack:** Python 3.12, deepagents 0.6.8, `langchain.agents.structured_output.ToolStrategy`, `langchain_openai.ChatOpenAI`, pytest.

---

## File Structure

- `src/services/chat/agents/ow_skills/synthesis/SKILL.md` — enriched: component-formula + clean-delimiter rules. **+ `references/formulas.md`** (offloaded formula catalogue).
- `src/services/chat/agents/ow_deepagents.py` — owns the deep-agent synthesizers. Adds `synthesize_structured` (A) and `synthesize_subagents_structured` (B) + a `_run_agent_structured` helper.
- `src/services/chat/agents/orchestrator_workers.py` — adds level-6/7 branches; `_aspects_from_answer` helper.
- `src/services/chat/agents/ow_harness.py` — `_MAX_IMPLEMENTED_LEVEL=7`; document 6/7.
- `src/services/chat/eval/structured_synth_compare.py` — **new**, lightweight A/B/C eval + metrics (kept separate from the heavy `ow_deepagents_compare.py`).
- Tests under `src/services/chat/tests/`.

No frontend / response-schema-field change.

---

## Task 1: Enriched synthesis skill + formula reference

**Files:**
- Modify: `src/services/chat/agents/ow_skills/synthesis/SKILL.md`
- Create: `src/services/chat/agents/ow_skills/synthesis/references/formulas.md`
- Test: `src/services/chat/tests/test_ow_harness.py`

- [ ] **Step 1: Write the failing contract test**

Add to `src/services/chat/tests/test_ow_harness.py`:

```python
def test_synthesis_skill_demands_component_formulas():
    from pathlib import Path
    base = Path(__file__).resolve().parents[1] / "agents" / "ow_skills" / "synthesis"
    md = (base / "SKILL.md").read_text(encoding="utf-8").lower()
    # component-formula rule + clean delimiter rule
    assert "component" in md and "formula" in md
    assert "$$" in md
    assert "never use plain-text" in md or "never plain-text" in md
    # the formula reference exists and is linked
    assert (base / "references" / "formulas.md").exists()
    assert "formulas.md" in md
```

- [ ] **Step 2: Run it, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py::test_synthesis_skill_demands_component_formulas -v`
Expected: FAIL (file/phrases absent).

- [ ] **Step 3: Create `references/formulas.md`**

```markdown
# Formula reference (load on demand)

State the *defining* formula of every component you name. Examples of the expected pattern:

- **Bias–variance** (a decomposition concept):
  - Bias: $\operatorname{Bias}(\hat f) = \mathbb{E}[\hat f] - f$
  - Variance: $\operatorname{Var}(\hat f) = \mathbb{E}\big[(\hat f - \mathbb{E}[\hat f])^2\big]$
  - Decomposition (central quantity): $$\operatorname{MSE}(\hat f) = \operatorname{Bias}(\hat f)^2 + \operatorname{Var}(\hat f) + \sigma^2$$
- **AR(p) / MA(q)** (a representation concept):
  - $Y_t = \phi_1 Y_{t-1} + \dots + \phi_p Y_{t-p} + \varepsilon_t$
  - $Y_t = \varepsilon_t + \theta_1 \varepsilon_{t-1} + \dots + \theta_q \varepsilon_{t-q}$

Rule: when a concept decomposes into named parts, each part's `###` subsection opens with a bullet stating that part's formula inline; a final `###` for the central quantity states the `$$decomposition$$`.
```

- [ ] **Step 4: Enrich `SKILL.md`**

Replace its `## Instructions` block with (keep the YAML frontmatter title/when-to-use; update `description` to include the keywords):

```markdown
---
name: synthesis
description: Integrate multiple authors' briefs into one comparative tutor answer with C-style bodies, component-defining LaTeX formulas ($...$ / $$...$$ math), and explicit author comparison.
---

# Synthesis skill

## When to use
When asked to synthesize author briefs (files under `/briefs/`) into a single tutor answer.

## Instructions
1. List `/briefs/` and READ every `/briefs/*.md` file in full before writing.
2. Write ONE coherent answer with a single throughline — not a per-author concatenation; COMPARE authors explicitly (agree / differ / why).
3. Retain every content-bearing key point; ground every claim in the briefs; never invent sources, formulas, or names. Skip "no-info" briefs.
4. STRUCTURE each subtopic for scanning: a short **bold lead sentence**, then **bold lead-in bullets** (`- **<claim>** — <explanation>`), one claim per line. Never a wall of text.
5. COMPONENT FORMULAS: when the concept decomposes into named components (e.g. bias / variance / MSE), give each component its own `### <Component>` whose first bullet STATES its defining formula inline, then a `### <central quantity>` stating the `$$decomposition$$`. See [formulas.md](references/formulas.md).
6. MATH DELIMITERS: inline `$...$`, display `$$...$$`. NEVER use plain-text math (write `$\alpha$`, not "alpha"); never emit `\(` or `\$(`.
7. Figures: keep any `[Fn]` figure marker from the briefs in the subtopic it belongs to.
```

- [ ] **Step 5: Run the test, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py::test_synthesis_skill_demands_component_formulas -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/ow_skills/synthesis/ src/services/chat/tests/test_ow_harness.py
git commit -m "feat(ow): synthesis skill demands component formulas + clean LaTeX delimiters"
```

---

## Task 2: Approach A — `synthesize_structured` (typed output, no schema-fill)

**Files:**
- Modify: `src/services/chat/agents/ow_deepagents.py`
- Test: `src/services/chat/tests/test_ow_deepagents_compare.py`

- [ ] **Step 1: Write the failing unit test (no network — stub the agent)**

Add to `src/services/chat/tests/test_ow_deepagents_compare.py`:

```python
def test_synthesize_structured_returns_typed_answer(monkeypatch):
    import asyncio
    import src.services.chat.agents.ow_deepagents as owd
    from src.services.chat.schemas.output import DeepTutorAnswer, AuthorBrief

    sentinel = DeepTutorAnswer(tldr="t", definition="d", formal_statement="",
                               example_intuition="e", applications="a", further_reading="f")

    class _Agent:
        def invoke(self, payload, config=None):
            return {"structured_response": sentinel, "messages": []}

    captured = {}
    def fake_create(**kwargs):
        captured.update(kwargs)
        return _Agent()
    monkeypatch.setattr(owd, "create_deep_agent", fake_create, raising=False)

    briefs = [AuthorBrief(author="Das", summary="s", key_points=["k"], source_ranks=[1])]
    out, it, ot = asyncio.run(owd.synthesize_structured("q", [], briefs, model="gpt-5.4-nano-2026-03-17"))
    assert out is sentinel
    assert captured.get("response_format") is not None      # typed output enforced
    assert captured.get("skills") == ["/skills/"]            # skill wired
```

(If `create_deep_agent` is imported lazily inside the function rather than at module top, monkeypatch the module attribute the function actually references — read the function and adjust the patch target. The behavioral asserts stay the same.)

- [ ] **Step 2: Run it, verify FAIL** (`synthesize_structured` undefined).

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py::test_synthesize_structured_returns_typed_answer -v`

- [ ] **Step 3: Implement `synthesize_structured`**

In `src/services/chat/agents/ow_deepagents.py`, add (mirror the store/skill preload of the existing `synthesize_with_skill`; reuse `_build_store`, `_sum_usage`, `SYNTHESIS_SKILL_DIR`, and the `_format_figure_bundle` import pattern):

```python
async def _run_agent_structured(agent, user_content):
    """Invoke a deep agent, returning (structured_response, in_tok, out_tok)."""
    from langchain_core.callbacks import UsageMetadataCallbackHandler
    cb = UsageMetadataCallbackHandler()
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user", "content": user_content}]},
        {"configurable": {"thread_id": "ow-struct"}, "callbacks": [cb]})
    structured = result.get("structured_response") if isinstance(result, dict) else None
    it, ot = _sum_usage(getattr(cb, "usage_metadata", None))
    return structured, it, ot


async def synthesize_structured(query, sources, briefs, *, model=None, figures=None):
    """Approach A: ONE deep agent emits a typed DeepTutorAnswer directly (no
    schema-fill). Returns (DeepTutorAnswer | None, in_tok, out_tok)."""
    try:
        import deepagents  # noqa: F401
        from deepagents import create_deep_agent
        from deepagents.backends import StoreBackend
        from deepagents.backends.utils import create_file_data
    except (ImportError, TypeError) as e:
        raise RuntimeError("pip install deepagents to run structured synthesis") from e
    from langchain_openai import ChatOpenAI
    from langchain.agents.structured_output import ToolStrategy
    from pathlib import Path
    from src.services.chat.schemas.output import DeepTutorAnswer
    from src.services.chat.prompts.deep_tutor import DEEP_TUTOR_INSTRUCTIONS
    from src.services.chat.agents.deep_tutor import _format_figure_bundle

    chosen = model or settings.openai_model_nano
    store = _build_store(briefs)
    skill_md = (Path(SYNTHESIS_SKILL_DIR) / "synthesis" / "SKILL.md").read_text(encoding="utf-8")
    store.put(namespace=("filesystem",), key="/skills/synthesis/SKILL.md",
              value=create_file_data(skill_md))
    ref = (Path(SYNTHESIS_SKILL_DIR) / "synthesis" / "references" / "formulas.md")
    if ref.exists():
        store.put(namespace=("filesystem",), key="/skills/synthesis/references/formulas.md",
                  value=create_file_data(ref.read_text(encoding="utf-8")))

    lc_model = ChatOpenAI(model=chosen, temperature=0.0, api_key=settings.openai_api_key)
    agent = create_deep_agent(
        model=lc_model, tools=[],
        system_prompt=DEEP_TUTOR_INSTRUCTIONS + "\n\nUse the synthesis skill. Read /briefs/*.md, then emit the DeepTutorAnswer.",
        backend=lambda rt: StoreBackend(rt), store=store, skills=["/skills/"],
        response_format=ToolStrategy(DeepTutorAnswer, handle_errors=True))
    user = f"Question: {query}\n\n{_format_figure_bundle(figures or [])}\n\nSynthesize the briefs into the DeepTutorAnswer now."
    return await _run_agent_structured(agent, user)
```

- [ ] **Step 4: Run the test, verify PASS.**

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/ow_deepagents.py src/services/chat/tests/test_ow_deepagents_compare.py
git commit -m "feat(ow): approach A synthesize_structured — deep agent emits typed DeepTutorAnswer (no schema-fill)"
```

---

## Task 3: Approach B — `synthesize_subagents_structured`

**Files:**
- Modify: `src/services/chat/agents/ow_deepagents.py`
- Test: `src/services/chat/tests/test_ow_deepagents_compare.py`

- [ ] **Step 1: Failing unit test**

```python
def test_synthesize_subagents_structured_builds_author_subagents(monkeypatch):
    import asyncio
    import src.services.chat.agents.ow_deepagents as owd
    from src.services.chat.schemas.output import DeepTutorAnswer, AuthorBrief

    sentinel = DeepTutorAnswer(tldr="t", definition="d", formal_statement="",
                               example_intuition="e", applications="a", further_reading="f")
    class _Agent:
        def invoke(self, payload, config=None):
            return {"structured_response": sentinel, "messages": []}
    captured = {}
    monkeypatch.setattr(owd, "create_deep_agent", lambda **kw: (captured.update(kw) or _Agent()), raising=False)

    briefs = [AuthorBrief(author="Das", summary="s", key_points=["k"], source_ranks=[1]),
              AuthorBrief(author="Pesaran", summary="s2", key_points=["k2"], source_ranks=[2])]
    out, it, ot = asyncio.run(owd.synthesize_subagents_structured("q", [], briefs, model="gpt-5.4-nano-2026-03-17"))
    assert out is sentinel
    subs = captured.get("subagents") or []
    assert len(subs) == 2                                  # one author-analyst per author
    assert all("response_format" in s for s in subs)       # subagents return typed AuthorBrief
    assert captured.get("response_format") is not None      # parent emits typed DeepTutorAnswer
```

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Implement `synthesize_subagents_structured`**

Mirror Task 2's setup; build one subagent per brief author and a parent `response_format`:

```python
async def synthesize_subagents_structured(query, sources, briefs, *, model=None, figures=None):
    """Approach B: ONE deep agent with one author-analyst subagent per author
    (each returns a typed AuthorBrief), then emits a typed DeepTutorAnswer.
    Returns (DeepTutorAnswer | None, in_tok, out_tok)."""
    try:
        import deepagents  # noqa: F401
        from deepagents import create_deep_agent
        from deepagents.backends import StoreBackend
        from deepagents.backends.utils import create_file_data
    except (ImportError, TypeError) as e:
        raise RuntimeError("pip install deepagents to run subagent synthesis") from e
    from langchain_openai import ChatOpenAI
    from langchain.agents.structured_output import ToolStrategy
    from pathlib import Path
    from src.services.chat.schemas.output import DeepTutorAnswer, AuthorBrief
    from src.services.chat.prompts.deep_tutor import DEEP_TUTOR_INSTRUCTIONS
    from src.services.chat.agents.deep_tutor import _format_figure_bundle

    chosen = model or settings.openai_model_nano
    store = _build_store(briefs)
    skill_md = (Path(SYNTHESIS_SKILL_DIR) / "synthesis" / "SKILL.md").read_text(encoding="utf-8")
    store.put(namespace=("filesystem",), key="/skills/synthesis/SKILL.md", value=create_file_data(skill_md))

    lc_model = ChatOpenAI(model=chosen, temperature=0.0, api_key=settings.openai_api_key)
    subagents = [{
        "name": f"author-{_slug(b.author)}",
        "description": f"Analyze author {b.author}'s brief at /briefs/{_slug(b.author)}.md and report their key points.",
        "system_prompt": f"Read /briefs/{_slug(b.author)}.md and return that author's faithful key points.",
        "skills": ["/skills/"],
        "response_format": AuthorBrief,
    } for b in briefs]
    agent = create_deep_agent(
        model=lc_model, tools=[], subagents=subagents,
        system_prompt=DEEP_TUTOR_INSTRUCTIONS + "\n\nDelegate each author's analysis to its author-analyst subagent, then synthesize into the DeepTutorAnswer.",
        backend=lambda rt: StoreBackend(rt), store=store, skills=["/skills/"],
        response_format=ToolStrategy(DeepTutorAnswer, handle_errors=True))
    user = f"Question: {query}\n\n{_format_figure_bundle(figures or [])}\n\nProduce the comparative DeepTutorAnswer now."
    return await _run_agent_structured(agent, user)
```

- [ ] **Step 4: Run the test, verify PASS.**

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/ow_deepagents.py src/services/chat/tests/test_ow_deepagents_compare.py
git commit -m "feat(ow): approach B synthesize_subagents_structured — author subagents + typed answer"
```

---

## Task 4: Harness levels 6/7 + routing branches

**Files:**
- Modify: `src/services/chat/agents/ow_harness.py`
- Modify: `src/services/chat/agents/orchestrator_workers.py`
- Test: `src/services/chat/tests/test_ow_harness.py`, `src/services/chat/tests/test_orchestrator_workers.py`

- [ ] **Step 1: Failing tests**

`test_ow_harness.py`:
```python
def test_levels_6_and_7_accepted(monkeypatch):
    import importlib, src.services.chat.agents.ow_harness as h
    for lvl in ("6", "7"):
        monkeypatch.setenv("TUTOR_OW_HARNESS", lvl)
        assert h.ow_harness_level() == int(lvl)
    monkeypatch.setenv("TUTOR_OW_HARNESS", "8")
    assert h.ow_harness_level() == 0
```

`test_orchestrator_workers.py` (mirror the existing deep-synth fallback tests):
```python
def test_level_6_routes_to_structured(monkeypatch):
    sources, plan = _two_author_inputs()
    async def fake_worker(query, thesis, author, srcs, *, model=None):
        from src.services.chat.schemas.output import AuthorBrief
        return AuthorBrief(author=author, summary=f"{author} s", key_points=[f"{author} kp"], source_ranks=[srcs[0].rank])
    monkeypatch.setattr(OW, "run_author_worker", fake_worker)
    monkeypatch.setenv("TUTOR_OW_HARNESS", "6")
    from src.services.chat.schemas.output import DeepTutorAnswer
    seen = {}
    async def fake_struct(query, srcs, briefs, *, model=None, figures=None):
        seen["A"] = True
        return DeepTutorAnswer(tldr="ok", definition="D", formal_statement="",
                               example_intuition="", applications="", further_reading=""), 1, 2
    import src.services.chat.agents.ow_deepagents as OWD
    monkeypatch.setattr(OWD, "synthesize_structured", fake_struct)
    deep, _ = asyncio.run(OW.run_orchestrator_workers("q", sources, plan))
    assert seen.get("A") and deep.definition == "D"
```

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Bump the harness max + document**

`ow_harness.py`: change `_MAX_IMPLEMENTED_LEVEL = 5` → `7`; update the module docstring level table to add:
```
  6 = deepagents structured synth (response_format=DeepTutorAnswer; no schema-fill)  (Approach A)
  7 = deepagents subagents + structured synth                                        (Approach B)
```

- [ ] **Step 4: Add the routing branches**

In `run_orchestrator_workers` (after computing `level` and building `briefs`, BEFORE the existing `deep_synth or level == 5` block), add `_aspects_from_answer` and the branches. First add the helper near the top of the module:

```python
_ASPECT_FIELDS = ("tldr", "definition", "formal_statement", "example_intuition", "applications", "further_reading")

def _aspects_from_answer(ans) -> dict[str, str]:
    """Build the aspect-text dict the caller expects from a finished answer."""
    return {f: (getattr(ans, f, "") or "") for f in _ASPECT_FIELDS}
```

Then the branches (resolve `synth_oa` the same way the `deep_synth` block does — coerce non-OpenAI → nano):
```python
    if level in (6, 7):
        try:
            from src.services.chat.agents import ow_deepagents
            from src.services.chat.llm.router import GROQ_MODEL_IDS  # noqa: PLC0415
            synth_oa = deep_synth_model or settings.openai_model_nano
            if synth_oa.startswith(("deepseek", "gemini", "qwen")) or synth_oa in GROQ_MODEL_IDS:
                synth_oa = settings.openai_model_nano
            fn = ow_deepagents.synthesize_structured if level == 6 else ow_deepagents.synthesize_subagents_structured
            deep_a, _it, _ot = await fn(query, sources, briefs, model=synth_oa, figures=figures)
            if deep_a is not None:
                return deep_a, _aspects_from_answer(deep_a)
            logger.info("ow level-%d structured synth returned None; falling back to L0", level)
        except Exception:  # noqa: BLE001
            logger.exception("ow level-%d structured synth failed; falling back to L0", level)
```

- [ ] **Step 5: Run the tests + full suite, verify PASS.**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py src/services/chat/tests/test_orchestrator_workers.py -q`

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/ow_harness.py src/services/chat/agents/orchestrator_workers.py src/services/chat/tests/test_ow_harness.py src/services/chat/tests/test_orchestrator_workers.py
git commit -m "feat(ow): harness levels 6/7 route to structured synth (A/B), no schema-fill"
```

---

## Task 5: Lightweight A/B/C eval + metrics

**Files:**
- Create: `src/services/chat/eval/structured_synth_compare.py`
- Test: `src/services/chat/tests/test_structured_synth_metrics.py`

- [ ] **Step 1: Failing metric tests**

Create `src/services/chat/tests/test_structured_synth_metrics.py`:
```python
from src.services.chat.eval.structured_synth_compare import (
    count_clean_math_violations, has_component_formulas, count_bullets,
)

def test_clean_math_violations():
    assert count_clean_math_violations("ok $x=1$ and $$y$$") == 0
    assert count_clean_math_violations(r"bad \$(x\)$ here") >= 1

def test_component_formulas():
    good = r"### Bias\n- **Bias** — $\operatorname{Bias}(\hat f)=E[\hat f]-f$\n### MSE\n$$\operatorname{MSE}=b^2+v+\sigma^2$$"
    assert has_component_formulas(good) is True
    assert has_component_formulas("bias is the error and variance is spread") is False

def test_count_bullets():
    assert count_bullets("- **A** — x\n- **B** — y\nplain") == 2
```

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Implement the eval module**

Create `src/services/chat/eval/structured_synth_compare.py`. Metrics:
```python
"""Lightweight A/B/C comparison for the structured-synth cycle (few calls).

Runs the bias-variance query through harness levels 5 (current C), 6 (A), 7 (B),
one run each, and scores clean-math / component-formulas / bullet-density /
latency / tokens. Needs deepagents installed + OPENAI_API_KEY. Run:
  .venv/bin/python -m src.services.chat.eval.structured_synth_compare
"""
from __future__ import annotations
import re

_BAD_MATH_RE = re.compile(r"\\\$\(|\\\)\$")
_BIAS_RE = re.compile(r"\\operatorname\{Bias\}|\bBias\b\s*[=(].*\$|\$[^$]*Bias")
_FORMULA_RE = re.compile(r"\$\$[^$]*\b(MSE|Bias|Var)\b[^$]*\$\$|\$[^$]*\\operatorname")

def count_clean_math_violations(text: str) -> int:
    return len(_BAD_MATH_RE.findall(text or ""))

def has_component_formulas(text: str) -> bool:
    t = text or ""
    # at least one inline component formula AND one display/central formula
    inline = bool(re.search(r"\$[^$]*\\operatorname|\$[^$]*=[^$]*\$", t))
    return inline and bool(_FORMULA_RE.search(t))

def count_bullets(text: str) -> int:
    return len(re.findall(r"(?m)^\s*-\s+\*\*", text or ""))
```

Then a `run()` that, for each level in (5, 6, 7): sets `TUTOR_OW_HARNESS`, calls `run_orchestrator_workers` on a frozen source bundle for "Compare how different authors define and motivate the bias-variance tradeoff." (reuse the source-freezing helper from `ow_deepagents_compare.py` or retrieve once and share across arms to save calls), times it, captures the returned `DeepTutorAnswer`, concatenates its aspect fields, computes the 3 metrics, and prints a table. Write the table to `docs/superpowers/eval/2026-06-04-structured-synth-compare.md`. Guard `__main__` so it only runs on explicit invocation (never in pytest).

- [ ] **Step 4: Run metric tests, verify PASS.**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_structured_synth_metrics.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/eval/structured_synth_compare.py src/services/chat/tests/test_structured_synth_metrics.py
git commit -m "feat(eval): lightweight A/B/C structured-synth comparison + metrics"
```

---

## Task 6: Run eval, wire winner, docs, verify

**Files:**
- Modify: `src/services/chat/agents/orchestrator_workers.py` (point `deep_synth`/`orchestrator-deep` at the winner)
- Modify: `docs/services/chat-features/56-deep-synthesis-l3b.md`, `docs/system/changelog.md`, `docs/system/invariants.md`

- [ ] **Step 1: Run the eval (3 LLM runs)**

Run: `.venv/bin/python -m src.services.chat.eval.structured_synth_compare`
Record the printed table (clean_math violations, has_component_formulas, bullet_count, latency, tokens per arm). **Winner = the arm with 0 clean-math violations AND component formulas present AND C-style bullets, at acceptable latency/cost.** Expected: A (level 6) wins (B's serial subagents cost more for no quality edge). If A and B tie on quality, pick A (cheaper). If BOTH structured arms fail validation repeatedly, report BLOCKED with the error.

- [ ] **Step 2: Wire the winner into the live deep path**

In `run_orchestrator_workers`, make the `deep_synth or level == 5` branch (the `orchestrator-deep` workflow) call the winning function instead of `synthesize_with_skill` + `_schema_fill`. Concretely: when `deep_synth` is requested, route to `synthesize_structured` (winner) and return `(answer, _aspects_from_answer(answer))`, with the existing L0 fallback on failure. Leave levels 5/6/7 intact for eval reproducibility.

- [ ] **Step 3: Docs lockstep**

- `docs/services/chat-features/56-deep-synthesis-l3b.md`: document levels 6/7, the structured-output topology (no schema-fill), the enriched formula skill, and paste the eval table + winner.
- `docs/system/changelog.md`: entry — structured synth replaces lossy schema-fill on the deep path; clean `$…$`; component formulas; eval winner.
- `docs/system/invariants.md`: note "orchestrator-deep emits a typed `DeepTutorAnswer` directly (winner level), no `_schema_fill` re-express".

- [ ] **Step 4: Full suite + manual verify**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q` → all green.
Then with `./scripts/dev.sh` running, one live `orchestrator-deep` run on the bias-variance question at :5175; confirm inline `$…$` renders cleanly (no literal `\$(`), and Bias/Variance/MSE appear as formulas in bullets. Note the result.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/orchestrator_workers.py docs/services/chat-features/56-deep-synthesis-l3b.md docs/system/changelog.md docs/system/invariants.md
git commit -m "feat(ow): wire structured-synth winner into orchestrator-deep; docs + eval table"
```

---

## Self-Review

- **Spec coverage:** enriched skill+formulas → T1; Approach A → T2; Approach B → T3; harness levels 6/7 + routing → T4; A/B/C eval + metrics → T5; run eval + wire winner + docs + verify → T6. All spec sections covered.
- **Placeholders:** none — every function body, test, and command is concrete. The one judgment step (winner pick, T6 S1) has an explicit decision rule + BLOCKED escape.
- **Type/name consistency:** `synthesize_structured` / `synthesize_subagents_structured` / `_run_agent_structured` / `_aspects_from_answer` / `count_clean_math_violations` / `has_component_formulas` / `count_bullets` are used identically across tasks. `DeepTutorAnswer` / `AuthorBrief` field names match `schemas/output.py`. `ToolStrategy(DeepTutorAnswer, handle_errors=True)` matches the confirmed import `langchain.agents.structured_output.ToolStrategy`. `create_deep_agent` accepts `response_format` + `subagents` (verified via signature).
