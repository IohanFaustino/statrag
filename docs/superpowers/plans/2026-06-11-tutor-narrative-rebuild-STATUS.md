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
| 5 | Non-interference tests (equations/citations/figures) | ✅ done (quality✅ + 2 fixes) | `aec5d26` + fix `19bc336` | caught + fixed real seams.py gap: strip `$$…$$`/`$…$` LaTeX from seam prose (tighter regex, no currency over-strip); component-equation invariant confirmed intact (incl. word-form variance path). |
| 6 | Frontend lockstep (scrub knob, collapse diagram) | ✅ done (spec✅ quality✅ + cleanup) | `c8aef94` + cleanup `60db894` | `tutorWorkflow` scrubbed everywhere; pipeline diagram collapsed to single "Narrative draft" node (retrieval-front + per-node model dropdowns kept); dead phase mappings + stale plan tooltip removed. 253 vitest pass, tsc clean. |
| 7 | Docs/HTML/invariants/changelog lockstep | ✅ done (accuracy✅ + 2 fixes) | `f404b85` + fixes `aa2b2d5`,`d6cfd7a` | doc 57 created; 44/48/56 superseded; 36 mermaid+env+schema; Elements/modes/tutor.html both diagrams; invariant 42 added + 18/34/35 retired + 37 updated; changelog; CLAUDE.md rows. Accuracy review caught 14 fabrications (nonexistent fn names, unbuilt blocklists, stale schema) — all corrected to match code. |
| — | FINAL whole-branch review (opus) | ✅ READY TO MERGE | `d8b9294` (3 minors fixed) | no Critical/Important; watchlist all accepted; `tutorWorkflow` symmetry total; invariant-bypass paths intact (redraft goes through same `_stream_draft` validators); Chinese wall intact. |
| 8 | Live verify (:5175 + browser as user) | ✅ PASS | — | bias-variance query on :5175: intro standalone w/ roadmap; Definition opens from thesis ("the tradeoff the thesis identifies…"); `### Bias` $$Bias(θ̂)=𝔼[θ̂]−θ$$ rendered (component-eq enforcement); "the intuition here is that…" present; **formalize beat auto-dropped (no theorem)**; 8 multi-author sources; citations + KaTeX render; **0 console errors**; persisted `quality={seam_continuity:1.0, lang_ok:1.0, thesis_adherence:1.0}` (all 3 scores wired to DB); modal shows single "Narrative draft" path + honest Planner copy + per-node dropdowns, no workflow selector — no drift. No redraft fired (first draft passed — good path; redraft path unit-tested). `rag-verify`: only pre-existing `page_from=-1` in introduction_textbooks (ingestion-era, unrelated). |

## Authoritative baseline
Worktree full chat suite at `19bc336` (backend complete, T1-5): **845 passed, 8 skipped, 0 failed** (run by orchestrator from the worktree).

## Known environment gotchas (verified)
- **Nested-worktree pytest count artifact:** subagents sometimes report ~897 total (they collect main's still-present OW tests because the worktree is physically nested under main). The ONLY authoritative count is the orchestrator's own run from the worktree pwd. What matters: **0 failures**. Always re-count personally.
- Harness pins shell/subagent cwd to the worktree; `cd` to main is auto-reset.
- `mypy` NOT installed in `.venv` → use `ruff` only.
- `.venv`, `.env`, `web/node_modules` are symlinks into the main checkout (set up at worktree creation).

## Final-review watchlist (re-examine in the whole-branch top-model review)
- `seams.py` `_last_sentence` thin-anchor fallback (unrequested in the fix task; accepted after orchestrator inspection — confirm it doesn't mask real disconnections / asymmetry with `_first_sentence`).
- Formula-recovery rewire: confirm `<recovered_equations>` actually lands verbatim in the relevant beat end-to-end (live, T8).
- **Prompt bloat:** `DEEP_TUTOR_INSTRUCTIONS` grew 20,301→21,696 chars; ceiling crept 20,500→22,000 across T3. Known quality risk (prompt dilution). Final review: assess whether the narrative additions can be tightened.
