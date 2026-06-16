# Tutor Formal Definitions + Promoted Wikipedia — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tutor answers reproduce every formal definition a source states *verbatim* (multiple allowed: strict + weak stationarity), and promote Wikipedia from augment-only to an interleaved source that may anchor definitions.

**Architecture:** Schema-only enrichment of the single narrative-draft call. A new tutor-only `TutorFormalDef` list carries verbatim definitions alongside the existing `formal_statement` prose beat (back-compat). Wikipedia sources interleave at real ranks and the prompt allows anchoring. No topology change, no new LLM call.

**Tech Stack:** Python 3.12 / Pydantic v2 (backend schema + validators), FastAPI SSE, React + TypeScript + Vitest + KaTeX (frontend), pytest (backend).

**Spec:** `docs/superpowers/specs/2026-06-16-tutor-formal-defs-and-wiki-promote-design.md`
**Base commit:** `f9a157a` on `feat/component-equation-enforcement`.

**Conventions for every task:** run backend tests with `.venv/bin/python -m pytest <path> -q`; frontend with `cd web && npx vitest run <path>`. Mode isolation (CLAUDE.md Chinese wall): the new model imports **nothing** from facilitate / qa / extension. Commit at the end of each task.

---

### Task 1: Schema — `TutorFormalDef` model + `formal_statements` field

**Files:**
- Modify: `src/services/chat/schemas/output.py` (add model before `DeepTutorAnswer` at line 153; add field after `formal_statement` ~line 191)
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write the failing test**

Add to `test_deep_tutor.py`:

```python
def test_tutor_formal_def_multi_and_verbatim():
    from src.services.chat.schemas.output import TutorFormalDef, DeepTutorAnswer
    strict = TutorFormalDef(kind="definition", label="Definition 14.1",
                            statement="A process is strictly stationary if $$F(x_{t_1},\\dots)=F(x_{t_1+h},\\dots)$$", cite=1)
    weak = TutorFormalDef(kind="definition", label="",
                          statement="A process is weakly stationary if $$E[x_t]=\\mu$$", cite=2)
    assert strict.label == "Definition 14.1"
    assert weak.label == ""          # unlabelled allowed
    ans = DeepTutorAnswer(tldr="t", definition="d", formal_statement="",
                          example_intuition="e", applications="a", further_reading="f",
                          formal_statements=[strict, weak])
    assert len(ans.formal_statements) == 2

def test_tutor_formal_def_empty_statement_rejected():
    import pytest
    from src.services.chat.schemas.output import TutorFormalDef
    with pytest.raises(Exception):
        TutorFormalDef(kind="definition", label="", statement="   ", cite=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_tutor_formal_def_multi_and_verbatim -q`
Expected: FAIL — `cannot import name 'TutorFormalDef'`.

- [ ] **Step 3: Write minimal implementation**

In `output.py`, add the model immediately before `class DeepTutorAnswer` (line 153). It must import nothing from other modes:

```python
class TutorFormalDef(BaseModel):
    """A formal definition/theorem reproduced VERBATIM from a tutor source.

    Brand-new to tutor mode — imports nothing from facilitate/qa/extension.
    Multiple allowed (e.g. strict + weak stationarity). A numbered label is
    preferred but not required; ``statement`` is the source's own wording."""
    kind: Literal["definition", "theorem", "proposition", "lemma", "corollary"]
    label: str = ""        # source's own label, e.g. "Definition 14.1"; "" when unlabelled
    statement: str = ""    # reproduced VERBATIM; display math in $$…$$
    cite: int              # [N] source rank backing this statement

    @model_validator(mode="after")
    def _statement_required(self) -> "TutorFormalDef":
        if not self.statement.strip():
            raise ValueError("TutorFormalDef.statement must not be empty")
        return self
```

Then add the field on `DeepTutorAnswer` right after `formal_statement` (after line 191):

```python
    formal_statements: list[TutorFormalDef] = Field(
        default_factory=list,
        description=(
            "Each formal definition/theorem a source states EXPLICITLY, reproduced "
            "VERBATIM (source wording + notation; display math in $$). Multiple "
            "allowed (e.g. strict AND weak stationarity). A numbered label is "
            "preferred but not required. Empty when no source states one."
        ),
    )
```

Confirm `Literal` is imported (it is used elsewhere in this file — check the top imports; add `from typing import Literal` only if absent).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -q`
Expected: PASS (both new tests + existing).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/schemas/output.py src/services/chat/tests/test_deep_tutor.py
git commit -m "feat(tutor): TutorFormalDef model + formal_statements field (verbatim, multi)"
```

---

### Task 2: Backend mapper — render `formal_statements[]` into the Formalize region

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py` (the `DeepTutorAnswer → TutorAnswer` assembly — find it with `grep -n "formal_statement\|def.*to_tutor\|aspects\|Formal" src/services/chat/agents/deep_tutor.py`; it assembles the markdown `text` and/or `aspects` from the beat fields)
- Test: `src/services/chat/tests/test_deep_tutor.py`

**Context:** The mapper assembles rendered markdown from the beat fields. The Formalize region currently uses only `formal_statement` (prose). Render the structured `formal_statements` list **after** that prose so the verbatim definitions appear under the same heading.

- [ ] **Step 1: Write the failing test**

```python
def test_formal_statements_render_into_markdown():
    from src.services.chat.agents.deep_tutor import _render_formal_statements
    from src.services.chat.schemas.output import TutorFormalDef
    defs = [
        TutorFormalDef(kind="definition", label="Definition 14.1",
                       statement="$$F(x_{t})=F(x_{t+h})$$", cite=1),
        TutorFormalDef(kind="definition", label="",
                       statement="$$E[x_t]=\\mu$$", cite=2),
    ]
    md = _render_formal_statements(defs)
    assert "Definition 14.1" in md
    assert "$$F(x_{t})=F(x_{t+h})$$" in md   # verbatim
    assert "$$E[x_t]=\\mu$$" in md
    assert "[1]" in md and "[2]" in md
    assert _render_formal_statements([]) == ""   # empty -> nothing
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_formal_statements_render_into_markdown -q`
Expected: FAIL — `cannot import name '_render_formal_statements'`.

- [ ] **Step 3: Write minimal implementation**

Add the helper to `deep_tutor.py` (near the other render/assembly helpers):

```python
def _render_formal_statements(defs: "list[TutorFormalDef]") -> str:
    """Render verbatim formal definitions as labelled blockquotes for the
    Formalize beat. Empty list -> empty string (heading dropped upstream)."""
    if not defs:
        return ""
    blocks = []
    for d in defs:
        head = d.label.strip() or d.kind.capitalize()
        blocks.append(f"> **{head}.** {d.statement.strip()} [{d.cite}]")
    return "\n>\n".join(blocks)
```

Then, in the mapper that assembles the Formalize section markdown, append the rendered list after the `formal_statement` prose. Locate the line that emits the formal beat into the assembled text and add (adapt variable names to the surrounding code):

```python
        _fs_extra = _render_formal_statements(getattr(answer, "formal_statements", []))
        if _fs_extra:
            formal_md = (formal_md + "\n\n" + _fs_extra) if formal_md.strip() else _fs_extra
```

Import `TutorFormalDef` in the `from ...schemas.output import (...)` block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "feat(tutor): render verbatim formal_statements under Formalize beat"
```

---

### Task 3: Prompt — relaxed multi formal-def instruction

**Files:**
- Modify: `src/services/chat/prompts/deep_tutor.py` (the `formal_statement` instruction block, ~lines 240–261, and the schema/aspect description block ~lines 181–190 if it documents the field list)
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_draft_prompt_instructs_verbatim_multi_formal_defs():
    from src.services.chat.prompts.deep_tutor import DRAFT_SYSTEM  # adapt: the draft system-prompt constant
    p = DRAFT_SYSTEM if isinstance(DRAFT_SYSTEM, str) else DRAFT_SYSTEM()
    low = p.lower()
    assert "formal_statements" in low          # new field documented
    assert "verbatim" in low
    # relaxed gate: numbered label no longer REQUIRED
    assert "not required" in low or "preferred but not" in low
```

(Adapt `DRAFT_SYSTEM` to the actual draft-prompt symbol — find it with `grep -n "def \|SYSTEM\|PROMPT\|formal_statement" src/services/chat/prompts/deep_tutor.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_draft_prompt_instructs_verbatim_multi_formal_defs -q`
Expected: FAIL — assertions on missing strings.

- [ ] **Step 3: Write minimal implementation**

Replace the conditional/numbered `formal_statement` instruction block with text covering the new list. Keep the prose `formal_statement` beat description (it stays as narrative connective tissue), and add a `formal_statements` paragraph:

```text
- ``formal_statements`` (list, may be empty): For EACH formal definition or
  theorem a source states EXPLICITLY, emit one entry reproducing it VERBATIM —
  the source's own wording and notation, display math in $$…$$. A numbered
  label ("Definition 14.1") is PREFERRED but NOT REQUIRED: an explicitly-phrased
  definition with no number still qualifies. Set ``label`` to the source's own
  label or "" when unlabelled; set ``kind`` accordingly; set ``cite`` to the
  [N] source rank. Reproduce MULTIPLE when a topic has several forms (e.g.
  strict AND weak stationarity each get their own entry). NEVER paraphrase into
  this field — paraphrase belongs in ``definition``. Empty list when no source
  states a formal definition.
```

Update the `formal_statement` prose-beat description so it no longer claims to be the *only* verbatim place (it now frames; `formal_statements` carries the verbatim text).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/prompts/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "feat(tutor): prompt — verbatim multi formal defs, relaxed gate"
```

---

### Task 4: Wikipedia — interleave at real ranks + bump per-concept lookup

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py` (`_append_wiki_sources` ~line 2512; `_fetch_wiki_sources` ~line 2478 for the lookup count)
- Test: `src/services/chat/tests/test_tutor_wiki.py`

**Context:** Current `_append_wiki_sources` puts all wiki sources at trailing ranks. Change to interleave so wiki appears among corpus ranks (visible, not buried). Keep corpus relative order.

- [ ] **Step 1: Write the failing test**

Add to `test_tutor_wiki.py`:

```python
def test_wiki_interleaved_not_all_trailing(monkeypatch):
    from src.services.chat.agents.deep_tutor import _append_wiki_sources
    from src.services.chat.schemas import Source
    def mk(book, rank): return Source(rank=rank, book=book, chapter="", section=f"s{rank}",
        title="t", excerpt="x", score=1.0, chunkId=f"{book}:{rank}", chunk="c", book_name=book, url="")
    corpus = [mk("hansen", i) for i in range(1, 7)]      # 6 corpus
    wiki = [mk("wikipedia", 0), mk("wikipedia", 0)]      # 2 wiki
    out = _append_wiki_sources(corpus, wiki)
    assert len(out) == 8
    ranks = [s.rank for s in out]
    assert ranks == sorted(ranks) and len(set(ranks)) == 8     # contiguous unique 1..8
    wiki_positions = [i for i, s in enumerate(out) if s.book == "wikipedia"]
    assert max(wiki_positions) < len(out) - 1     # at least one wiki is NOT the last element
    corpus_order = [s.chunkId for s in out if s.book == "hansen"]
    assert corpus_order == [f"hansen:{i}" for i in range(1, 7)]   # corpus relative order kept
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_wiki.py::test_wiki_interleaved_not_all_trailing -q`
Expected: FAIL — current impl trails all wiki at the end (`max(wiki_positions) == len-1`).

- [ ] **Step 3: Write minimal implementation**

Rewrite `_append_wiki_sources` to interleave (insert one wiki after every ~3 corpus, remainder appended), then renumber ranks contiguously:

```python
def _append_wiki_sources(corpus: list[Source], wiki: list[Source]) -> list[Source]:
    """Interleave wiki sources among corpus (visible, not trailing-only).
    Corpus relative order preserved; ranks renumbered 1..N contiguously."""
    if not wiki:
        return corpus
    merged: list[Source] = []
    wi = iter(wiki)
    nxt = next(wi, None)
    for i, c in enumerate(corpus, start=1):
        merged.append(c)
        if i % 3 == 0 and nxt is not None:   # one wiki after every 3 corpus
            merged.append(nxt)
            nxt = next(wi, None)
    while nxt is not None:                    # remainder
        merged.append(nxt)
        nxt = next(wi, None)
    for r, s in enumerate(merged, start=1):   # contiguous renumber
        s.rank = r
    return merged
```

Bump the per-concept lookup in `_fetch_wiki_sources`: where it builds `wiki_evidence(c, subject_id=c)` per concept, take up to 2 evidences per concept instead of 1 (slice `[:2]` on the returned list before mapping). Keep dedupe by title.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_wiki.py -q`
Expected: PASS (new + existing 5; if an existing test asserted strict trailing append, update it to the interleave contract — corpus relative order + contiguous ranks).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_tutor_wiki.py
git commit -m "feat(tutor): interleave Wikipedia sources + bump per-concept lookup"
```

---

### Task 5: Wikipedia — prompt allows anchoring

**Files:**
- Modify: `src/services/chat/prompts/deep_tutor.py` (the wiki render/instruction block ~lines 758–766)
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_wiki_prompt_allows_anchor():
    # render the source bundle with a wikipedia source and assert the instruction
    # no longer forbids anchoring.
    from src.services.chat.prompts.deep_tutor import render_sources_block  # adapt to actual fn
    from src.services.chat.schemas import Source
    w = Source(rank=2, book="wikipedia", chapter="", section="Stationarity", title="Stationarity",
               excerpt="...", score=0.0, chunkId="wiki:Stationarity", chunk="...",
               book_name="Wikipedia", url="https://en.wikipedia.org/wiki/Stationary_process")
    block = render_sources_block([w]).lower()
    assert "never to override" not in block and "supplementary" not in block
    assert "may anchor" in block or "anchor the" in block
```

(Adapt `render_sources_block` to the actual function that renders sources for the draft prompt — find with `grep -n "wikipedia\|def .*source\|supplementary" src/services/chat/prompts/deep_tutor.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py::test_wiki_prompt_allows_anchor -q`
Expected: FAIL — old "supplementary / never to override" text present.

- [ ] **Step 3: Write minimal implementation**

Replace the wiki source label/instruction. Old (~lines 758–766) says supplementary, cite "only for breadth/definitions, never to override a textbook". New:

```python
        if src.book == "wikipedia":
            lines.append(
                f"<source rank='{src.rank}' chunkId='{src.chunkId}' kind='wikipedia'>\n"
                f"[#{src.rank}] Wikipedia — {src.section}:\n"
                f"{body}\n"
                f"</source>"
            )
```

And in the static instruction paragraph for sources, replace the "never override" rule with: *"Wikipedia sources (🌐) are valid evidence. Prefer the textbook corpus where it covers the concept, but when the corpus lacks a clean formal definition you MAY anchor the ``definition`` (and a ``formal_statements`` entry, if Wikipedia states one verbatim) on Wikipedia, cited by its [N]."*

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/prompts/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "feat(tutor): prompt — Wikipedia may anchor definitions"
```

---

### Task 6: Frontend — type + render `formal_statements[]`

**Files:**
- Modify: `web/src/types.ts` (add `TutorFormalDef` type + `formal_statements` on the tutor answer type)
- Modify: `web/src/components/views/TutorView.tsx` and/or `web/src/lib/mapConversationMessages.ts` (render the list under the Formal heading; fall back to legacy `formal_statement` string when list empty)
- Test: `web/src/components/MessageThread.test.tsx` (or the existing TutorView render test)

- [ ] **Step 1: Write the failing test**

Add a render test asserting both verbatim statements appear with labels and KaTeX is invoked. Mirror the existing tutor-answer render test setup in `MessageThread.test.tsx`:

```tsx
it("renders multiple verbatim formal definitions", () => {
  const answer = makeTutorAnswer({
    formal_statements: [
      { kind: "definition", label: "Definition 14.1", statement: "$$F(x_t)=F(x_{t+h})$$", cite: 1 },
      { kind: "definition", label: "", statement: "$$E[x_t]=\\mu$$", cite: 2 },
    ],
  });
  render(<TutorView answer={answer} /* …existing props… */ />);
  expect(screen.getByText(/Definition 14.1/)).toBeInTheDocument();
  expect(screen.getByText(/Definition/)).toBeInTheDocument();   // unlabelled -> kind heading
});
```

(Adapt `makeTutorAnswer` / `TutorView` props to the existing test helpers in the file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/components/MessageThread.test.tsx`
Expected: FAIL — list not rendered.

- [ ] **Step 3: Write minimal implementation**

In `types.ts`:

```ts
export interface TutorFormalDef {
  kind: "definition" | "theorem" | "proposition" | "lemma" | "corollary";
  label: string;
  statement: string;
  cite: number;
}
```

Add `formal_statements?: TutorFormalDef[]` to the tutor answer interface.

In the render path, after the existing formal-statement render, map `formal_statements` to labelled blocks (reuse the existing math/markdown renderer used for other sections — do NOT hand-roll KaTeX):

```tsx
{(answer.formal_statements ?? []).map((d, i) => (
  <blockquote key={i} className="formal-def">
    <strong>{d.label || capitalize(d.kind)}.</strong>{" "}
    <MathMarkdown text={d.statement} /> <cite>[{d.cite}]</cite>
  </blockquote>
))}
```

Keep the legacy `formal_statement` string render as the fallback when `formal_statements` is empty.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/components/MessageThread.test.tsx` then `cd web && npx tsc --noEmit`
Expected: PASS + no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/types.ts web/src/components/views/TutorView.tsx web/src/lib/mapConversationMessages.ts web/src/components/MessageThread.test.tsx
git commit -m "feat(tutor): frontend renders verbatim formal_statements list"
```

---

### Task 7: Lockstep — modal + docs + HTML

**Files:**
- Modify: `web/src/data/tutorPipeline.ts`, `web/src/components/PipelineDiagram.tsx` (+ `PipelineDiagram.test.tsx`)
- Modify: `docs/services/chat-features/36-deep-tutor.md`, `docs/services/chat-features/57-tutor-narrative.md`
- Modify: `docs/system/invariants.md`, `docs/system/changelog.md`
- Modify: `docs/common ground/Elements/modes/tutor.html`

- [ ] **Step 1: Update the modal data + diagram**

In `tutorPipeline.ts`: update the draft node label/desc to note it emits **verbatim formal definitions** (`formal_statements`), and the Wikipedia node to **"anchor + interleave"** (was augment-only/trailing). If a test asserts node labels (`PipelineDiagram.test.tsx`), update it in lockstep.

- [ ] **Step 2: Run the diagram test**

Run: `cd web && npx vitest run src/components/PipelineDiagram.test.tsx`
Expected: PASS.

- [ ] **Step 3: Update docs (markdown)**

- `36-deep-tutor.md`: schema note for `formal_statements`; mermaid wiki node "anchor + interleave"; confirm `TUTOR_DEEP_WIKI` env row present.
- `57-tutor-narrative.md`: Formalize beat now carries a `formal_statements` verbatim list.
- `invariants.md`: add/adjust the tutor formal-statement invariant to cover verbatim multi + that `formal_statements[].statement` is non-empty.
- `changelog.md`: top entry describing both changes.

- [ ] **Step 4: Update HTML doc**

`docs/common ground/Elements/modes/tutor.html`: reflect the same two changes (verbatim formal defs; Wikipedia anchor + interleave) so HTML matches markdown + modal.

- [ ] **Step 5: Full gate + commit**

Run backend + frontend suites:
```bash
.venv/bin/python -m pytest src/services/chat/tests -q
cd web && npx vitest run && npx tsc --noEmit
```
Expected: all green, no type errors.

```bash
git add web/src/data/tutorPipeline.ts web/src/components/PipelineDiagram.tsx web/src/components/PipelineDiagram.test.tsx docs/
git commit -m "docs(tutor): lockstep modal + docs + HTML for formal defs & wiki promotion"
```

---

## Self-Review

**Spec coverage:** Part A (multi verbatim, relaxed gate, brand-new model) → T1–T3, T6. Part B (interleave, bump lookup, anchor) → T4–T5. Lockstep (modal/docs/HTML/tests) → T7. Live gate is post-plan orchestration (browser certify). All spec sections mapped.

**Placeholder scan:** Code blocks are concrete; "adapt to actual symbol" notes are grep-guided (mapper/prompt-constant/render-fn names not knowable without the file open) — the implementer locates the exact line with the given grep, not a TODO.

**Type consistency:** `TutorFormalDef{kind,label,statement,cite}` identical across backend (T1), backend render (T2), frontend type (T6). `formal_statements` field name consistent everywhere. `_render_formal_statements`/`_append_wiki_sources` signatures consistent T2/T4.
