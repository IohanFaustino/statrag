# Tutor Narrative Rebuild — Orchestrator Status

Worktree: `.claude/worktrees/tutor-narrative-rebuild` (branch `worktree-tutor-narrative-rebuild`, based on HEAD `d46ecd5` of `feat/component-equation-enforcement`).
Spec: `docs/superpowers/specs/2026-06-11-tutor-narrative-rebuild-design.md` · Plan: `…/2026-06-11-tutor-narrative-rebuild.md`.
Implementers: `voltagent-lang:python-pro` (sonnet). Reviewers: general-purpose (sonnet). Roster per task: implementer → spec review → quality review → fixes.

## Task tracker
| # | Task | Status | Commit | Notes |
|---|---|---|---|---|
| 1 | Deletion sweep + formula-recovery rewire | ✅ done (spec✅ quality✅) | `448a4d9` + cleanup `62d6d3d` | 7 variants → 1 draft; OW/deepagents/organize/harness deleted; `tutorWorkflow` knob gone; formula recovery rewired into `_stream_draft` via `_recover_equations_block`. |
| 2 | Seam validator `agents/seams.py` (pure code) | ✅ done (spec✅ quality✅) | `1cb4d30` + fixes `5432496` | expanded `_GENERIC` (fixed "into" false-match); splitter ignores abbreviations; `_last_sentence` thin-anchor fallback (WATCHLIST). |
| 3 | Narrative prompt + per-beat Field descriptions | ⏳ next | — | |
| 4 | Wire seam guard + bounded redraft + thesis injection | ⏳ | — | T4 Step 6 = verify TutorView final-payload-overwrites-stream (BLOCKING). |
| 5 | Non-interference tests (equations/citations/figures) | ⏳ | — | |
| 6 | Frontend lockstep (scrub knob, collapse diagram) | ⏳ | — | |
| 7 | Docs/HTML/invariants/changelog lockstep | ⏳ | — | |
| 8 | Live verify (:5175 + Google MCP as user) | ⏳ orchestrator-run | — | |

## Authoritative baseline
Worktree full chat suite at `5432496`: **833 passed, 8 skipped, 0 failed** (run by orchestrator from the worktree).

## Known environment gotchas (verified)
- **Nested-worktree pytest count artifact:** subagents sometimes report ~897 total (they collect main's still-present OW tests because the worktree is physically nested under main). The ONLY authoritative count is the orchestrator's own run from the worktree pwd. What matters: **0 failures**. Always re-count personally.
- Harness pins shell/subagent cwd to the worktree; `cd` to main is auto-reset.
- `mypy` NOT installed in `.venv` → use `ruff` only.
- `.venv`, `.env`, `web/node_modules` are symlinks into the main checkout (set up at worktree creation).

## Final-review watchlist (re-examine in the whole-branch top-model review)
- `seams.py` `_last_sentence` thin-anchor fallback (unrequested in the fix task; accepted after orchestrator inspection — confirm it doesn't mask real disconnections / asymmetry with `_first_sentence`).
- Formula-recovery rewire: confirm `<recovered_equations>` actually lands verbatim in the relevant beat end-to-end (live, T8).
