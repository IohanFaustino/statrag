# Tutor Citation Binder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace heuristic tutor citation repair with a pure-code chunk-placeholder binder that produces exact `[N]` citations from real retrieved sources.

**Architecture:** Tutor draft generation will stop emitting raw `[N]` markers and instead emit `[[c:<chunkId>]]` placeholders tied to source bundle identities. A single backend binder in `deep_tutor.py` will rewrite placeholders to sequential `[N]`, build `TutorCitation[]` from matching `Source` rows, and remove unresolved placeholders without guessing. Formal-definition rendering will route through the same binder path.

**Tech Stack:** Python 3.12, FastAPI chat backend, Pydantic models, pytest, existing tutor pipeline in `src/services/chat/agents/deep_tutor.py`

---

## File Map

- Modify: `src/services/chat/prompts/deep_tutor.py`
  - Update tutor prompt contract to require `[[c:<chunkId>]]` placeholders instead of raw `[N]` markers.
  - Ensure source bundle formatting exposes `chunkId` clearly enough for the model to reuse.

- Modify: `src/services/chat/agents/deep_tutor.py`
  - Add the pure-code tutor binder.
  - Route final assembled tutor text through the binder.
  - Remove remaining heuristic citation fallback logic for tutor mode.
  - Adapt formal-definition rendering to participate in the same binder path.

- Modify: `src/services/chat/schemas/output.py`
  - Only if needed for small compatibility fields or comments; avoid schema churn unless necessary.

- Modify: `src/services/chat/tests/test_tutor_prompt_contract.py`
  - Lock in the new placeholder-based prompt contract.

- Modify: `src/services/chat/tests/test_deep_tutor.py`
  - Add binder unit tests and finalization-path tests.

- Modify: `docs/system/invariants.md`
  - Replace the heuristic citation invariant with the placeholder-binding invariant.

- Modify: `docs/services/chat-features/36-deep-tutor.md`
  - Update the tutor stage description to reflect pure-code citation binding.

- Modify: `docs/common ground/Elements/modes/tutor.html`
  - Keep HTML docs in sync with the markdown docs.

- Optional modify: `web/src/data/tutorMode.ts`
  - Only if the in-app modal text claims the old behavior rather than the new binder.

---

### Task 1: Lock the New Prompt Contract

**Files:**
- Modify: `src/services/chat/prompts/deep_tutor.py`
- Test: `src/services/chat/tests/test_tutor_prompt_contract.py`

- [ ] **Step 1: Write the failing prompt-contract test**

Add assertions to `src/services/chat/tests/test_tutor_prompt_contract.py` that the tutor prompt:

```python
def test_tutor_prompt_requires_chunk_placeholders_for_citations():
    assert "[[c:<chunkid>]]" in INSTR or "[[c:" in INSTR
    assert "forbid raw [n]" in INSTR or "do not write raw [n]" in INSTR
    assert "chunkid" in INSTR
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest src/services/chat/tests/test_tutor_prompt_contract.py::test_tutor_prompt_requires_chunk_placeholders_for_citations -q
```

Expected: FAIL because the prompt still describes raw `[N]`-style output rather than chunk placeholders.

- [ ] **Step 3: Write minimal prompt change**

Edit `src/services/chat/prompts/deep_tutor.py` so the tutor instructions say:

```python
# In the citation-format rules for tutor drafting:
- Do NOT write raw `[N]` citation markers in tutor mode.
- For every grounded claim, cite with `[[c:<chunkId>]]` using a `chunkId` taken verbatim from the `<source_bundle>`.
- Reuse the same `[[c:<chunkId>]]` token whenever the same source supports multiple claims.
- Never invent a `chunkId` that is not present in the `<source_bundle>`.
```

Also update the source-bundle formatting text so each source shows its `chunkId` plainly.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest src/services/chat/tests/test_tutor_prompt_contract.py::test_tutor_prompt_requires_chunk_placeholders_for_citations -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/prompts/deep_tutor.py src/services/chat/tests/test_tutor_prompt_contract.py
git commit -m "test: lock tutor chunk placeholder citation contract"
```

### Task 2: Add the Pure-Code Tutor Binder

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py`
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write the failing binder tests**

Add tests to `src/services/chat/tests/test_deep_tutor.py`:

```python
def test_bind_tutor_citations_numbers_by_first_appearance(sample_sources):
    from src.services.chat.agents.deep_tutor import bind_tutor_citations
    text = (
        f"Claim A [[c:{sample_sources[2].chunkId}]]. "
        f"Claim B [[c:{sample_sources[0].chunkId}]]. "
        f"Claim C [[c:{sample_sources[2].chunkId}]]."
    )
    out_text, cites, meta = bind_tutor_citations(text, sample_sources)
    assert out_text.count("[1]") == 2
    assert out_text.count("[2]") == 1
    assert cites[0].chunkId == sample_sources[2].chunkId
    assert cites[1].chunkId == sample_sources[0].chunkId


def test_bind_tutor_citations_does_not_guess_unresolved_ids(sample_sources):
    from src.services.chat.agents.deep_tutor import bind_tutor_citations
    text = "Claim A [[c:missing-source]]."
    out_text, cites, meta = bind_tutor_citations(text, sample_sources)
    assert "[[c:missing-source]]" not in out_text
    assert cites == []
    assert meta["unbound_citations"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest \
  src/services/chat/tests/test_deep_tutor.py::test_bind_tutor_citations_numbers_by_first_appearance \
  src/services/chat/tests/test_deep_tutor.py::test_bind_tutor_citations_does_not_guess_unresolved_ids -q
```

Expected: FAIL because `bind_tutor_citations` does not exist yet.

- [ ] **Step 3: Write minimal binder implementation**

Add to `src/services/chat/agents/deep_tutor.py`:

```python
_TUTOR_CITE_RE = re.compile(r"\[\[c:([^\]]+)\]\]")


def bind_tutor_citations(text: str, sources: list[Source]) -> tuple[str, list[TutorCitation], dict[str, int]]:
    by_chunk = {s.chunkId: s for s in sources if s.chunkId}
    order: dict[str, int] = {}
    citations: list[TutorCitation] = []
    unbound = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal unbound
        chunk_id = match.group(1).strip()
        src = by_chunk.get(chunk_id)
        if src is None:
            unbound += 1
            return ""
        if chunk_id not in order:
            idx = len(order) + 1
            order[chunk_id] = idx
            citations.append(TutorCitation(
                index=idx,
                chunkId=src.chunkId,
                authors_short=src.authors_short,
                year=src.year,
                book_name=src.book_name or src.book,
                chapter=src.chapter,
                section=src.section,
                page_from=src.page_from,
                page_to=src.page_to,
                quote=(src.excerpt or "")[:200],
                url=getattr(src, "url", "") or "",
            ))
        return f"[{order[chunk_id]}]"

    bound_text = _TUTOR_CITE_RE.sub(repl, text)
    return bound_text, citations, {"unbound_citations": unbound}
```

ponytail: do not add retry logic here; keep the binder deterministic and small.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest \
  src/services/chat/tests/test_deep_tutor.py::test_bind_tutor_citations_numbers_by_first_appearance \
  src/services/chat/tests/test_deep_tutor.py::test_bind_tutor_citations_does_not_guess_unresolved_ids -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "feat: add pure-code tutor citation binder"
```

### Task 3: Route Final Tutor Output Through the Binder

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py`
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write the failing finalization test**

Add:

```python
def test_convert_to_tutor_answer_uses_bound_chunk_placeholders(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    deep = _make_deep_answer(
        definition=f"A definition sentence [[c:{sample_sources[0].chunkId}]]",
        formal_statement="",
    )
    ans = _convert_to_tutor_answer(deep, {}, sample_sources)
    assert "[[c:" not in ans.text
    assert "[1]" in ans.text
    assert len(ans.citations) == 1
    assert ans.citations[0].chunkId == sample_sources[0].chunkId
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_convert_to_tutor_answer_uses_bound_chunk_placeholders -q
```

Expected: FAIL because `_convert_to_tutor_answer` does not yet bind placeholders.

- [ ] **Step 3: Write minimal finalization change**

In `_convert_to_tutor_answer`:

```python
text = assemble_markdown(final_aspects)
text, bound_cites, bind_meta = bind_tutor_citations(text, sources)
headings = [ASPECT_HEADINGS[k] for k in ASPECT_HEADINGS if final_aspects[k].strip()]

raw_cites = list(deep.citations) if deep else []
enriched = _reconcile_citations(raw_cites, sources)
if bound_cites:
    enriched = bound_cites
else:
    enriched = _ensure_marker_citations(text, enriched, sources)
```

And fold `bind_meta["unbound_citations"]` into `quality`.

ponytail: keep the old `_ensure_marker_citations` path only as a temporary fallback for legacy stored drafts, not for the new placeholder flow.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_convert_to_tutor_answer_uses_bound_chunk_placeholders -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "feat: route tutor finalization through citation binder"
```

### Task 4: Remove Heuristic Tutor Citation Guessing

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py`
- Test: `src/services/chat/tests/test_tutor_prompt_contract.py`
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write the failing anti-guessing tests**

Use or extend existing tests so they assert:

```python
def test_ensure_marker_citations_does_not_guess_missing_sources():
    ...


def test_reconcile_citations_does_not_guess_by_index_rank(sample_sources):
    ...
```

These tests already exist in current work; ensure they are active and failing if heuristic fallback is restored.

- [ ] **Step 2: Run tests to verify current behavior target**

Run:

```bash
.venv/bin/python -m pytest \
  src/services/chat/tests/test_tutor_prompt_contract.py::test_ensure_marker_citations_does_not_guess_missing_sources \
  src/services/chat/tests/test_deep_tutor.py::test_reconcile_citations_does_not_guess_by_index_rank -q
```

Expected: PASS after binder work. If either fails, the fallback logic is still too permissive.

- [ ] **Step 3: Simplify the heuristic helpers**

In `src/services/chat/agents/deep_tutor.py`:

- keep `_ensure_marker_citations` as a no-guess filter for legacy `[N]`
- keep `_reconcile_citations` chunk/url-only
- do not fall back to rank or `sources[0]`

The target shape is:

```python
def _ensure_marker_citations(text, enriched, sources):
    markers = ...
    if not markers:
        return []
    return sorted([c for c in enriched if c.index in set(markers)], key=lambda c: c.index)
```

and `_reconcile_citations` should only enrich when `chunkId` or exact `url` matches a real `Source`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest \
  src/services/chat/tests/test_tutor_prompt_contract.py::test_ensure_marker_citations_does_not_guess_missing_sources \
  src/services/chat/tests/test_deep_tutor.py::test_reconcile_citations_does_not_guess_by_index_rank -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_tutor_prompt_contract.py src/services/chat/tests/test_deep_tutor.py
git commit -m "refactor: remove tutor citation guessing fallbacks"
```

### Task 5: Bind Formal Statements Through the Same Path

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py`
- Modify: `src/services/chat/agents/definition_recovery.py` (only if a helper is needed)
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write the failing formal-statement binder test**

Add:

```python
def test_formal_statement_uses_chunk_placeholder_binding(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    from src.services.chat.schemas.output import TutorFormalDef

    deep = _make_deep_answer(
        formal_statement="",
        formal_statements=[
            TutorFormalDef(kind="definition", label="Definition 1", statement=f"A formal statement [[c:{sample_sources[1].chunkId}]]", cite=99)
        ],
    )
    ans = _convert_to_tutor_answer(deep, {}, sample_sources)
    assert "[[c:" not in ans.aspects["formal_statement"]
    assert "[1]" in ans.aspects["formal_statement"]
    assert ans.citations[0].chunkId == sample_sources[1].chunkId
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_formal_statement_uses_chunk_placeholder_binding -q
```

Expected: FAIL until formal rendering emits placeholders that the binder resolves.

- [ ] **Step 3: Write minimal rendering change**

Update `_render_formal_statements` so it can render binder-ready placeholders from real source identity. Minimal version:

```python
def _render_formal_statements(defs) -> str:
    if not defs:
        return ""
    blocks = []
    for d in defs:
        head = (d.label or "").strip() or d.kind.capitalize()
        blocks.append(f"**{head}.**\n\n{d.statement.strip()}")
    return "\n\n".join(blocks)
```

and ensure the `statement` passed into `TutorFormalDef` can carry `[[c:<chunkId>]]` when built from recovered defs or downstream formatting.

If needed, add a tiny helper that converts recovered defs to binder-ready statement strings before final assembly.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_formal_statement_uses_chunk_placeholder_binding -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "feat: bind tutor formal statements through citation binder"
```

### Task 6: Update Docs and Invariants in Lockstep

**Files:**
- Modify: `docs/system/invariants.md`
- Modify: `docs/services/chat-features/36-deep-tutor.md`
- Modify: `docs/common ground/Elements/modes/tutor.html`
- Optional Modify: `web/src/data/tutorMode.ts`

- [ ] **Step 1: Write the doc/invariant deltas**

Update `docs/system/invariants.md` to replace the heuristic tutor citation statement with:

```md
Tutor citations are placeholder-bound by pure code: every inline `[N]` originates from a bound `[[c:<chunkId>]]` placeholder, every `TutorCitation.index == N` maps to the exact retrieved `Source.chunkId`, and unresolved placeholders are removed, never guessed.
```

Update `docs/services/chat-features/36-deep-tutor.md` and `docs/common ground/Elements/modes/tutor.html` to describe tutor citation binding as a pure-code stage after drafting.

If `web/src/data/tutorMode.ts` still claims the old heuristic behavior, update the modal text to say the tutor answer binds citations deterministically from retrieved source ids.

- [ ] **Step 2: Review the doc surfaces manually**

Check that markdown, HTML, and modal text say the same thing.

Expected: all three surfaces describe chunk-placeholder citation binding and no heuristic guessing.

- [ ] **Step 3: Commit**

```bash
git add docs/system/invariants.md docs/services/chat-features/36-deep-tutor.md "docs/common ground/Elements/modes/tutor.html" web/src/data/tutorMode.ts
git commit -m "docs: document tutor pure-code citation binder"
```

### Task 7: End-to-End Verification

**Files:**
- Verify: backend + live app

- [ ] **Step 1: Run the targeted tutor backend suite**

Run:

```bash
.venv/bin/python -m pytest src/services/chat/tests/test_definition_recovery.py src/services/chat/tests/test_tutor_prompt_contract.py src/services/chat/tests/test_deep_tutor.py -q
```

Expected: PASS.

- [ ] **Step 2: Run a live backend stationarity check**

Run a fresh live tutor query against the backend and inspect the stored conversation artifact.

Command:

```bash
.venv/bin/python - <<'PY'
import json, urllib.request
base = 'http://127.0.0.1:8766'
msg = 'What is stationarity? What are the forms? What are the statistical tests used to assess stationarity?'
create_payload = {"mode":"tutor","title":msg,"model_id":"gpt-5.4-nano-2026-03-17","book_filter":"ALL"}
create_req = urllib.request.Request(base + '/api/conversations', data=json.dumps(create_payload).encode(), headers={'Content-Type':'application/json'}, method='POST')
with urllib.request.urlopen(create_req, timeout=30) as r:
    conv = json.loads(r.read().decode())
payload = {'conversationId': conv['id'], 'message': msg, 'mode': 'tutor', 'model': 'gpt-5.4-nano-2026-03-17', 'bookFilter': 'ALL', 'temperature': None, 'top_k': None, 'rerank': None, 'stageModels': {'plan': 'deepseek-v4-pro', 'draft': 'deepseek-v4-pro'}, 'diversityAuthors': 'auto'}
chat_req = urllib.request.Request(base + '/api/chat', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json','Accept':'text/event-stream'}, method='POST')
with urllib.request.urlopen(chat_req, timeout=240) as r:
    _ = r.read()
conv_req = urllib.request.Request(base + f'/api/conversations/{conv["id"]}')
with urllib.request.urlopen(conv_req, timeout=30) as r:
    full = json.loads(r.read().decode())
assistant = [m for m in full['messages'] if m['role'] == 'assistant'][-1]
content = assistant['content'] if isinstance(assistant['content'], dict) else json.loads(assistant['content'])
formal = content.get('aspects', {}).get('formal_statement', '')
assert '![image](' not in formal
assert 'Failed to generate an answer' not in content.get('text', '')
assert len(content.get('citations', [])) > 0
print('live tutor check ok')
PY
```

Expected: `live tutor check ok`.

- [ ] **Step 3: Verify in browser on `:5175`**

Use the live app with the stationarity prompt and confirm:

- no OCR image placeholders in the Formal statement section
- references open to the actual supporting entries
- no `Failed to generate an answer`

Expected: manual browser verification passes.

- [ ] **Step 4: Commit final integration**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/prompts/deep_tutor.py src/services/chat/tests/test_tutor_prompt_contract.py src/services/chat/tests/test_deep_tutor.py docs/system/invariants.md docs/services/chat-features/36-deep-tutor.md "docs/common ground/Elements/modes/tutor.html" web/src/data/tutorMode.ts
git commit -m "feat: bind tutor citations from source chunk ids"
```

---

## Self-Review

- Spec coverage: prompt contract, binder, heuristic removal, formal-statement integration, docs, invariants, and live verification are all mapped to tasks.
- Placeholder scan: no `TODO` / `TBD` / “appropriate handling” placeholders remain.
- Type consistency: binder works on `Source.chunkId`, returns `TutorCitation[]`, and leaves frontend payload shape unchanged.
