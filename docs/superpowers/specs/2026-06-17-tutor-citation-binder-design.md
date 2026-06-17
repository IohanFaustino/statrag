# Tutor Citation Binder Design

Date: 2026-06-17
Status: proposed
Scope: tutor mode only

## Problem

Tutor mode still lets the model imply citation identity, then tries to repair the result heuristically. This causes citation drift:

- inline `[N]` markers can point at the wrong source
- missing citation objects are guessed from source order or rank
- formal-statement citations and prose citations do not share one deterministic binding path

This is not fixable by better prompting alone. The trust boundary is wrong.

## Goal

Make tutor citations true-by-construction:

- the model writes prose and source placeholders only
- pure code assigns final citation numbers
- `TutorCitation[]` is built only from real retrieved sources
- unresolved citations are never guessed

## Non-goals

- no frontend redesign; final payload still uses `[N]`
- no cross-mode rewrite for QA/facilitate/resume in this task
- no new retrieval step during binding

## Recommendation

Use chunk-backed placeholders in tutor drafts:

- model writes `[[c:<chunkId>]]`
- backend binds placeholders to first-seen citation numbers `[1] [2] ...`
- backend builds `TutorCitation[]` directly from matching `Source` rows

This is preferred over rank-backed placeholders because `chunkId` is a stable identity while rank can change after rerank, augmentation, or source merging.

## Alternatives Considered

### 1. Chunk placeholder binder (recommended)

Format:

```text
Weak stationarity requires a constant mean and lag-only autocovariance. [[c:400c85f7-ee13-5d52-a5f5-2decd9b54b0d]]
```

Pros:

- stable identity
- true-by-construction citation mapping
- survives source reorder / rerank
- matches existing `Source.chunkId`

Cons:

- prompt and finalizer changes required
- tutor draft output must stop writing raw `[N]`

### 2. Rank placeholder binder

Format:

```text
Weak stationarity requires a constant mean. [[r:4]]
```

Pros:

- slightly simpler prompt

Cons:

- fragile when ranks change
- less future-proof than `chunkId`

### 3. Post-hoc citation audit only

Keep model-authored `[N]` and verify after generation.

Pros:

- smallest patch

Cons:

- still true-by-instruction
- catches errors but does not prevent them
- preserves the bad trust boundary

## Proposed Architecture

### Prompt Contract

Tutor prompt changes:

- forbid direct `[N]` markers in model output
- require every grounded claim to use `[[c:<chunkId>]]`
- require reuse of the same placeholder when the same source supports multiple claims
- forbid invented source ids

The source bundle shown to the model must include visible `chunkId` values for each source.

### Binding Pass

Add a pure-code binder in tutor finalization.

Proposed function:

```python
bind_tutor_citations(text: str, sources: list[Source]) -> tuple[str, list[TutorCitation], dict[str, int]]
```

Behavior:

1. Scan `text` for `[[c:<chunkId>]]` in appearance order.
2. First-seen unique `chunkId` gets the next citation number.
3. Replace every placeholder occurrence with the assigned `[N]`.
4. Build `TutorCitation` from the matching `Source`.
5. Repeated occurrences of the same `chunkId` reuse the same number.
6. Preserve citation order by first appearance in prose.

### Failure Policy

If a placeholder does not resolve to a real `Source`:

- do not guess from rank, order, or first source
- remove the unresolved placeholder from rendered text
- increment a quality/lint counter such as `unbound_citations`

Optional recovery:

- if unresolved placeholders are non-zero, allow one best-effort redraft
- if unresolved placeholders remain after redraft, keep the answer but surface the lint internally

ponytail: the first implementation should remove unresolved placeholders and record lint only; no retry loop unless needed.

### Formal Statement Integration

Recovered formal definitions should use the same binder path.

Instead of pre-numbering formal-definition citations by integer alone, render formal statements with chunk placeholders derived from recovered-definition `chunkId`:

```text
**Definition 14.1.**

A time series process ... [[c:400c85f7-ee13-5d52-a5f5-2decd9b54b0d]]
```

That makes prose citations and formal-definition citations share one deterministic binding system.

Short term compatibility:

- keep `TutorFormalDef.cite` if needed for existing code
- derive binder output from `chunkId` where available
- prefer placeholder binding over prefilled integer citation ids

## Backend Changes

### `src/services/chat/prompts/deep_tutor.py`

- update instructions to require `[[c:<chunkId>]]` instead of `[N]`
- explicitly forbid raw `[N]` markers in tutor draft output
- ensure source bundle includes visible `chunkId`

### `src/services/chat/agents/deep_tutor.py`

- add `bind_tutor_citations(...)`
- run binder after aspect assembly and before final `TutorAnswer`
- remove tutor-specific heuristic repair behavior:
  - no positional fill-in for missing citations
  - no fallback from citation index to source rank
  - no fallback to `sources[0]`

### `src/services/chat/schemas/output.py`

- keep `TutorCitation` output shape unchanged for frontend compatibility
- no user-visible schema break required in phase 1

### Frontend

No structural change required if final tutor text still contains `[N]` and `TutorCitation[]` remains aligned.

## Data Flow

New tutor citation flow:

1. retrieval builds `augmented_sources`
2. prompt includes source bundle with `chunkId`
3. model emits tutor prose with `[[c:<chunkId>]]`
4. backend assembles final markdown text
5. binder rewrites placeholders to `[N]`
6. binder builds exact `TutorCitation[]`
7. frontend renders unchanged

## Invariants

Add / update tutor invariant:

- every tutor inline `[N]` marker must originate from a real bound placeholder, not heuristic synthesis
- every `TutorCitation.index == N` must map to the exact `Source.chunkId` referenced by the original placeholder
- unresolved placeholders are removed, never guessed

## Testing

### Unit tests

Add tests for:

- repeated same `chunkId` -> same `[N]`
- first appearance order determines numbering
- unresolved placeholder is removed, not guessed
- mixed valid + invalid placeholders preserve valid citations
- formal-definition placeholder binds through the same binder

### Regression tests

Replace current tests that encode heuristic repair behavior.

Specifically:

- no auto-fill from marker position
- no rank-based fallback when `chunkId` is missing

### Live verification

Stationarity prompt:

`What is stationarity? What are the forms? What are the statistical tests used to assess stationarity?`

Expected:

- no OCR image placeholders in formal statement
- inline references map to the actual supporting sources
- formal statements and prose use the same citation numbering contract

## Rollout Plan

### Phase 1

- add binder
- update prompt
- remove heuristic citation guessing
- keep frontend unchanged

### Phase 2

- migrate formal-definition rendering fully to placeholder-based binding
- optionally add one redraft retry for unresolved placeholders if live quality requires it

## Risks

### Model may emit malformed placeholders

Mitigation:

- strict prompt examples
- binder ignores malformed tokens
- unit tests for malformed input

### Output may temporarily lose citations if the model under-cites

Mitigation:

- this is preferable to wrong citations
- track `unbound_citations` / missing-binding metrics
- improve prompt after correctness is locked

### Formal-definition code path may partially duplicate binder behavior

Mitigation:

- keep one shared binder function
- avoid separate numbering logic per aspect

## Acceptance Criteria

- tutor mode no longer guesses missing citations from source order, rank, or first source
- final `[N]` markers come only from bound placeholders
- `TutorCitation[]` matches the bound placeholder sources exactly
- stationarity prompt produces clean formal definitions without OCR image placeholders
- targeted tutor backend tests pass
- live tutor verification on `:5175` confirms correct binding behavior
