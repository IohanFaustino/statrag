# Tutor Render And Citation Pendings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the three active tutor pendings together: formal statement markdown rendering, citation numbering consistency, and citation pill hyperlinking.

**Architecture:** Keep the backend authoritative for the final tutor markdown and citation numbering, then make the lightweight frontend parser respect those boundaries without adding a markdown library. Prefer the smallest edits in `_render_formal_statements`, `_convert_to_tutor_answer`, and `TutorView.splitIntoBlocks`/citation click handling.

**Tech Stack:** Python 3.12, pytest, pydantic; TypeScript, React 18, Vite, Vitest, Testing Library; browser verification on `:5175`.

---

### Task 1: Backend authority for formal statement markdown and citation numbering

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py`
- Modify: `src/services/chat/prompts/deep_tutor.py`
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write the failing backend tests for the final-text citation contract**

Add these tests near the existing citation/formal-statement block in `src/services/chat/tests/test_deep_tutor.py`:

```python
def test_render_formal_statements_separates_multiple_blocks_with_blank_quote_lines():
    from src.services.chat.agents.deep_tutor import _render_formal_statements
    from src.services.chat.schemas.output import TutorFormalDef

    defs = [
        TutorFormalDef(
            kind="definition",
            label="Definition 14.1",
            statement="$$F(x_t)=F(x_{t+h})$$",
            cite=1,
        ),
        TutorFormalDef(
            kind="definition",
            label="Definition 14.2",
            statement="$$E[x_t]=\\mu$$",
            cite=2,
        ),
    ]

    md = _render_formal_statements(defs)
    assert "> **Definition 14.1.** $$F(x_t)=F(x_{t+h})$$" in md
    assert ">" in md
    assert "\n>\n\n> **Definition 14.2.**" in md


def test_convert_to_tutor_answer_numbers_citations_by_final_text_order(sample_sources):
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    from src.services.chat.schemas.output import TutorFormalDef

    deep = _make_deep_answer(
        definition=(
            f"Definition prose first [[c:{sample_sources[2].chunkId}]]."
        ),
        formal_statement="",
        example_intuition=(
            f"Example second [[c:{sample_sources[0].chunkId}]]."
        ),
        formal_statements=[
            TutorFormalDef(
                kind="definition",
                label="Definition 1",
                statement=f"Formal third [[c:{sample_sources[1].chunkId}]].",
                cite=99,
            )
        ],
    )

    ans = _convert_to_tutor_answer(deep, {}, sample_sources)

    assert ans.citations[0].chunkId == sample_sources[2].chunkId
    assert ans.citations[1].chunkId == sample_sources[1].chunkId
    assert ans.citations[2].chunkId == sample_sources[0].chunkId
    assert "Definition prose first [1]." in ans.text
    assert "Formal third [2]." in ans.text
    assert "Example second [3]." in ans.text
```

- [ ] **Step 2: Run the backend tests to verify they fail first**

Run:

```bash
.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -k "render_formal_statements or final_text_order" -v
```

Expected: FAIL, showing the current formal-statement separator and/or citation ordering does not satisfy the new assertions.

- [ ] **Step 3: Make `_render_formal_statements` emit stable blockquote blocks**

Update `src/services/chat/agents/deep_tutor.py` in `_render_formal_statements` to build each block separately, then join them with an explicit blank quoted line plus a real blank line between blocks:

```python
def _render_formal_statements(defs) -> str:
    if not defs:
        return ""
    blocks: list[str] = []
    for d in defs:
        head = (d.label or "").strip() or d.kind.capitalize()
        body = d.statement.strip()
        blocks.append(f"> **{head}.** {body}")
    return "\n>\n\n".join(blocks)
```

Keep the function local and boring. Do not append `[d.cite]` or add a second citation path.

- [ ] **Step 4: Ensure citation binding still happens after final markdown assembly**

In `src/services/chat/agents/deep_tutor.py`, keep or restore this sequence inside `_convert_to_tutor_answer`:

```python
    text = assemble_markdown(final_aspects)
    bound_text, citations, meta = bind_tutor_citations(text, sources)
```

If the current code binds on anything earlier than `assemble_markdown(final_aspects)`, change it back so first appearance in final text defines numbering.

If `assemble_markdown` needs stronger block separation for the formal statement section, make only this minimal change in `src/services/chat/prompts/deep_tutor.py`:

```python
def assemble_markdown(aspects: dict[str, str]) -> str:
    out: list[str] = []
    for key, heading in ASPECT_HEADINGS.items():
        body = (aspects.get(key) or "").strip()
        if not body:
            continue
        out.append(f"## {heading}\n\n{body}")
    return "\n\n".join(out).strip()
```

Only touch `assemble_markdown` if inspection shows it is part of the bug; otherwise leave it alone.

- [ ] **Step 5: Re-run the backend tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -k "render_formal_statements or final_text_order or chunk_placeholder_binding" -v
```

Expected: PASS for the new tests and the nearby existing citation/formal-statement tests.

- [ ] **Step 6: Commit the backend slice**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/prompts/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "fix(tutor): stabilize formal statement citations"
```


### Task 2: Frontend parser and citation-link robustness

**Files:**
- Modify: `web/src/components/views/TutorView.tsx`
- Modify: `web/src/components/views/TutorView.blocks.test.tsx`
- Modify: `web/src/components/views/TutorView.citations.test.tsx`

- [ ] **Step 1: Write the failing frontend tests for block and anchor behavior**

Extend `web/src/components/views/TutorView.blocks.test.tsx` with a regression that proves a quote block flushes cleanly before a following display-math block:

```tsx
it("flushes a quote block before a following $$ display-math block", () => {
  const blocks = splitIntoBlocks(
    "## Formal statement\n\n> **Definition 14.1.** Strict stationarity. [1]\n>\n\n$$F(x_t)=F(x_{t+h})$$\n\nAfter.",
  );
  expect(blocks.map((b) => b.kind)).toEqual(["h2", "quote", "math", "para"]);
});
```

Extend `web/src/components/views/TutorView.citations.test.tsx` with a regression that proves explicit citation indexes, not array position, drive the links:

```tsx
it("uses the explicit citation index for hrefs instead of array position", () => {
  const cites = new Map([
    [7, { index: 7, book_name: "Stats 101", chapter: "Ch3", authors_short: "Freedman", year: 2009 }],
  ]);
  const html = render("See [7].", cites as any);
  expect(html).toContain('href="#cite-7"');
  expect(html).not.toContain('href="#cite-1"');
});
```

- [ ] **Step 2: Run the frontend tests to verify they fail first**

Run:

```bash
npm test -- --run web/src/components/views/TutorView.blocks.test.tsx web/src/components/views/TutorView.citations.test.tsx
```

from `web/`.

Expected: FAIL, showing the parser and/or citation rendering does not yet satisfy the new cases.

- [ ] **Step 3: Tighten `splitIntoBlocks` around quote/list/math boundaries**

In `web/src/components/views/TutorView.tsx`, make the flush order explicit when a structural block starts. The important shape is:

```tsx
    if (listMatch) {
      flushQuote();
      flushPara();
      ...
    } else if (listBuf) {
      flushList();
    }

    if (quoteMatch) {
      flushList();
      flushPara();
      ...
    } else if (quoteBuf) {
      flushQuote();
    }

    if (imgMatch) {
      flushList();
      flushQuote();
      flushPara();
      ...
    }

    if (stripped.startsWith("### ")) {
      flushList();
      flushQuote();
      flushPara();
      ...
    } else if (stripped.startsWith("## ")) {
      flushList();
      flushQuote();
      flushPara();
      ...
    } else if (stripped.startsWith("$$") && stripped.endsWith("$$") && stripped.length > 4) {
      flushList();
      flushQuote();
      flushPara();
      ...
    } else if (stripped.startsWith("$$")) {
      flushList();
      flushQuote();
      flushPara();
      ...
    } else if (stripped === "") {
      flushList();
      flushQuote();
      flushPara();
    }
```

The goal is not a rewrite. Just ensure one block type cannot leak into the next.

- [ ] **Step 4: Keep citation behavior index-based and safe on repeated clicks**

In `web/src/components/views/TutorView.tsx`, keep the existing `Map<number, TutorCitation>` pattern and make only minimal robustness edits if needed:

```tsx
  const citationsByIndex = React.useMemo(() => {
    const m = new Map<number, TutorCitation>();
    for (const c of data.citations ?? []) m.set(c.index, c);
    return m;
  }, [data.citations]);

  const onCite = React.useCallback((idx: number) => {
    const present = (data.citations ?? []).some((c) => c.index === idx);
    if (!present) return;
    setSourcesOpen(true);
    try { window.history.replaceState(null, "", `#cite-${idx}`); } catch {}
    window.setTimeout(() => {
      const el = document.getElementById(`cite-${idx}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        setHoveredIdx(idx);
      }
    }, 60);
  }, [data.citations]);
```

Do not add array-position fallback logic.

- [ ] **Step 5: Re-run the frontend tests to verify they pass**

Run:

```bash
npm test -- --run web/src/components/views/TutorView.blocks.test.tsx web/src/components/views/TutorView.citations.test.tsx
```

from `web/`.

Expected: PASS.

- [ ] **Step 6: Commit the frontend slice**

```bash
git add web/src/components/views/TutorView.tsx web/src/components/views/TutorView.blocks.test.tsx web/src/components/views/TutorView.citations.test.tsx
git commit -m "fix(tutor): harden tutor view citation rendering"
```


### Task 3: End-to-end verification and required surface updates

**Files:**
- Modify if needed: `CLAUDE.md`
- Modify if needed: `docs/services/chat-features/36-deep-tutor.md`
- Modify if needed: `docs/common ground/Elements/modes/tutor.html`

- [ ] **Step 1: Run the focused backend and frontend checks together**

Run:

```bash
.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -k "render_formal_statements or final_text_order or chunk_placeholder_binding" -v
```

from repo root, and:

```bash
npm test -- --run web/src/components/views/TutorView.blocks.test.tsx web/src/components/views/TutorView.citations.test.tsx
```

from `web/`.

Expected: PASS on both commands.

- [ ] **Step 2: Start or confirm the dev app on :5175**

Run:

```bash
./scripts/dev.sh
```

Expected: backend on `:8766`, Vite on `:5175`.

- [ ] **Step 3: Browser-verify the three pendings on live tutor output**

In the browser on `http://localhost:5175`:

1. open tutor mode,
2. use a prompt that tends to produce formal statements, for example `What is strict stationarity?`,
3. inspect the answer.

Confirm all of these:

- formal statement blocks show as proper quote/definition content,
- no raw `>` markers leak into prose,
- display equations render as KaTeX,
- inline `[N]` markers match the Sources panel numbering,
- clicking the same `[N]` twice still opens and scrolls correctly,
- clicking a different `[N]` scrolls to the matching `id="cite-N"` row.

- [ ] **Step 4: Update docs only if the implementation changed user-visible tutor behavior wording**

If the fix only restores intended behavior, do not churn docs. If any visible rule or invariant text changes, update all required surfaces together:

```text
CLAUDE.md
docs/services/chat-features/36-deep-tutor.md
docs/common ground/Elements/modes/tutor.html
```

Keep the edit to a short clarification about tutor citation/index contract or formal statement rendering; do not rewrite the feature docs.

- [ ] **Step 5: Run final status and diff review**

Run:

```bash
rtk git status --short
```

and:

```bash
rtk git diff -- src/services/chat/agents/deep_tutor.py src/services/chat/prompts/deep_tutor.py src/services/chat/tests/test_deep_tutor.py web/src/components/views/TutorView.tsx web/src/components/views/TutorView.blocks.test.tsx web/src/components/views/TutorView.citations.test.tsx CLAUDE.md docs/services/chat-features/36-deep-tutor.md "docs/common ground/Elements/modes/tutor.html"
```

Expected: only the intended files for this bundled fix are present.

- [ ] **Step 6: Commit the verification/docs slice**

```bash
git add CLAUDE.md docs/services/chat-features/36-deep-tutor.md "docs/common ground/Elements/modes/tutor.html"
git add src/services/chat/agents/deep_tutor.py src/services/chat/prompts/deep_tutor.py src/services/chat/tests/test_deep_tutor.py web/src/components/views/TutorView.tsx web/src/components/views/TutorView.blocks.test.tsx web/src/components/views/TutorView.citations.test.tsx
git commit -m "fix(tutor): close render and citation pendings"
```
