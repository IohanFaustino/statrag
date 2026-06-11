# Tutor Narrative Rebuild — Orchestrator Status

Worktree: `.claude/worktrees/tutor-narrative-rebuild` (branch `worktree-tutor-narrative-rebuild`, based on HEAD `d46ecd5` of `feat/component-equation-enforcement`).
Spec: `docs/superpowers/specs/2026-06-11-tutor-narrative-rebuild-design.md` · Plan: `…/2026-06-11-tutor-narrative-rebuild.md`.
Implementers: `voltagent-lang:python-pro` (sonnet). Reviewers: general-purpose (sonnet). Roster per task: implementer → spec review → quality review → fixes.

## Task tracker
| # | Task | Status | Commit | Notes |
|---|---|---|---|---|
| 1 | Deletion sweep + formula-recovery rewire | ✅ done (spec✅ quality✅) | `448a4d9` + cleanup `62d6d3d` | 7 variants → 1 draft; OW/deepagents/organize/harness deleted; `tutorWorkflow` knob gone; formula recovery rewired into `_stream_draft` via `_recover_equations_block`. |
| 2 | Seam validator `agents/seams.py` (pure code) | ✅ done (spec✅ quality✅) | `1cb4d30` + fixes `5432496` | expanded `_GENERIC` (fixed "into" false-match); splitter ignores abbreviations; `_last_sentence` thin-anchor fallback (WATCHLIST). |
| 3 | Narrative prompt + per-beat Field descriptions | ✅ done (spec✅ quality✅ + re-review) | `9950b53` + fix `5bb928a` | bridge-opener contract on all 4 threaded beats reconciled w/ Field descriptions; worker-tasks stripped from SYNTHESIS_PLAN_PROMPT; tightened plan-task test. |
| 4 | Wire seam guard + bounded redraft + thesis injection | ✅ done (spec✅ quality✅ + I1 fix) | `76796ed` + fix `a7def86` | seam guard wired in run_deep_tutor; ONE non-streamed redraft; composite acceptance (no lang/boilerplate regress); thesis `<thesis>` injected; quality scores merged. BLOCKING Step 6 RESOLVED by orchestrator: TutorView renders final `structured_output.data.text` (TutorView.tsx:139), not streamed tokens → silent redraft valid. |
| 5 | Non-interference tests (equations/citations/figures) | ⏳ next | — | |
| 6 | Frontend lockstep (scrub knob, collapse diagram) | ⏳ | — | |
| 7 | Docs/HTML/invariants/changelog lockstep | ⏳ | — | |
| 8 | Live verify (:5175 + Google MCP as user) | ⏳ orchestrator-run | — | |

## Authoritative baseline
Worktree full chat suite at `5bb928a`: **835 passed, 8 skipped, 0 failed** (run by orchestrator from the worktree).

## Known environment gotchas (verified)
- **Nested-worktree pytest count artifact:** subagents sometimes report ~897 total (they collect main's still-present OW tests because the worktree is physically nested under main). The ONLY authoritative count is the orchestrator's own run from the worktree pwd. What matters: **0 failures**. Always re-count personally.
- Harness pins shell/subagent cwd to the worktree; `cd` to main is auto-reset.
- `mypy` NOT installed in `.venv` → use `ruff` only.
- `.venv`, `.env`, `web/node_modules` are symlinks into the main checkout (set up at worktree creation).

## Final-review watchlist (re-examine in the whole-branch top-model review)
- `seams.py` `_last_sentence` thin-anchor fallback (unrequested in the fix task; accepted after orchestrator inspection — confirm it doesn't mask real disconnections / asymmetry with `_first_sentence`).
- Formula-recovery rewire: confirm `<recovered_equations>` actually lands verbatim in the relevant beat end-to-end (live, T8).
- **Prompt bloat:** `DEEP_TUTOR_INSTRUCTIONS` grew 20,301→21,696 chars; ceiling crept 20,500→22,000 across T3. Known quality risk (prompt dilution). Final review: assess whether the narrative additions can be tightened.
