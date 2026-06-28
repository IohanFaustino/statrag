# Pending Work Registry

> Generated/maintained as the pending-work registry; CLAUDE.md links here. Update this file as items close. Last updated 2026-06-28.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Done / merged |
| 🟢 | Backend built (live-confirmed) |
| 🟡 | Recovered / needs verify |
| 🟠 | Known issue |
| ⬜ | Not started |

---

# PART A — Feature / pipeline pending work

## A1. Tutor finalize+verify stage

| Field | Value |
|---|---|
| **Status** | ✅ DONE + MERGED into `feat/component-equation-enforcement` (merge `fe67ce7`, 2026-06-18); branch + worktree cleaned up. |
| **Result** | Green: backend 1106 passed / 3 skipped; frontend 334 passed; tsc clean. |
| **Mechanism** | Two routes converge on one `TutorAnswer`: gpt = structured · deepseek/gemini = tolerant. Route badge shown in footer. Best-effort — failed finalize keeps the draft. Env `TUTOR_FINALIZE` (default OFF) · `TUTOR_FINALIZE_MODEL` (default `gpt-5.4` full). |
| **Math-delimiting bug** | FIXED (`0c0df49`): frontend bare-math wrap catches `letter_{…}` / `letter^…` atoms across all routes; pixel-verified on :5175 — the AR(1) formal statement renders `y_t=φ₀+φ₁y_{t−1}+ε_t` fully, no literal leak. |
| **Model switch verified** | Finalize stage → DeepSeek V4 Pro → badge flips to `Finalized · deepseek-v4-pro · tolerant`; answer renders. |
| **Decision** | `TUTOR_FINALIZE` stays opt-in (default OFF). |

### Remaining (opt-in path, NOT blocking)

| # | Severity | Issue | Root cause |
|---|---|---|---|
| a | 🟠 | **deepseek tolerant-route raw-LaTeX leak.** Complex defs (e.g. "Definition 6.32 causal graphical model") render raw `\mathbf{P A}` / `\prod_` / space-separated `x _ {j}`. | DeepSeek emits malformed / un-`$`-delimited multiline math. The gpt structured route is clean. |
| b | 🟠 | **component-equation-enforcement validator rejects both nano draft + deepseek finalize** on math-heavy questions (missing `$$display equation$$` per definition subsection). | Triggers ~30s of best-effort retries before it recovers and renders. |

### References

- Spec: `docs/superpowers/specs/2026-06-17-tutor-finalize-stage-design.md`
- Plan: `docs/superpowers/plans/2026-06-17-tutor-finalize-stage.md`
- Doc: `docs/services/chat-features/59-tutor-finalize.md`

### Next action

Address (a) by hardening the tolerant-route math delimiter on the deepseek path (mirror the gpt structured cleanup), or fall back to structured route for math-heavy definitions. Address (b) by relaxing the validator's per-definition `$$…$$` requirement when the question is not strictly definitional.

---

## A2. Tutor multi-question facet contract (scope A)

| Field | Value |
|---|---|
| **Status** | ✅ DONE + MERGED into `feat/component-equation-enforcement` (merge `3ebec42`, 2026-06-18); branch + worktree cleaned up. |
| **Mechanism** | Pure-code change: `multi_question_split` + `concepts_from_asks` + `augment_concepts_and_facets` union each question's subject into concepts (→ definition recovery) and asks into facets (→ coverage + finalize). `_MAX_GAPS` raised 3 → 5. So an N-question prompt decomposes and each subject reaches the detector. |
| **Tests** | Full chat suite green (9 new tests). |
| **Live-verified** | :5175, prompt *"What is stationarity? What are its versions? What is a unit root?"* → answer decomposes into STATIONARITY / UNIT ROOT / INTEGRATED VERSIONS I(0)-vs-I(1) subsections woven by an Introduction. The original "doesn't decompose multi-question prompts" complaint is FIXED. |

### Remaining → Definition Recovery follow-up (NOT scope A)

| Severity | Issue | Root cause |
|---|---|---|
| 🟠 | **Verbatim strict/weak/unit-root formal-definition BOXES did not render.** "Versions" surfaced as I(0)/I(1) instead of strict/weak, and the Formal-statement box held only the AR(p) equation plus a small trailing `$$` leak. | Live retrieval already pulls definition prose, so `_has_labelled_def` → "not a gap" → the dedicated verbatim recovery path is suppressed. The regression test used empty sources so it never caught this. |

This gap converges with A3's DR-5 + DR-8(c) — see the note under A3. Those two items together = "make verbatim strict/weak/unit-root definition boxes actually render", the single highest-priority open piece.

### References

- Spec: `docs/superpowers/specs/2026-06-18-tutor-multiquestion-facet-contract-design.md`
- Plan: `docs/superpowers/plans/2026-06-18-tutor-multiquestion-facet-contract.md`

### Next action

Implement DR-5 (frontend structured render) + DR-8(c) (force strict/weak/covariance gap concepts even when prose is present). See A3.

---

## A3. Tutor: Definition Recovery (DR)

| Field | Value |
|---|---|
| **Status** | 🟢 BACKEND BUILT + live-confirmed (2026-06-16); 30 tests green. |
| **Goal** | Treat verbatim formal definitions as premium info: gap-detect → dedicated definition retrieval → verbatim extract + pure-code token-recall gate → code-built `formal_statements[]`. |
| **Env** | `TUTOR_DEEP_DEFINITIONS`. |

**This is the highest-leverage open feature.**

### Remaining

| # | Status | Work |
|---|---|---|
| DR-5 | ⬜ | **Frontend structured render of `formal_statements[]`.** Verbatim definition boxes do not render today. |
| DR-6 | ⬜ | **Docs/modal lockstep.** Write `docs/services/chat-features/58-definition-recovery.md` and sync the modal/diagram surfaces. |
| DR-8 | ⬜ | **Quality:** (a) statement truncation; (b) prefer clean-text defs over OCR-image ones; (c) gap concepts must include strict/weak/covariance forms EVEN WHEN general retrieval already pulled definition prose (live 2026-06-18: `_has_labelled_def` → "not a gap" suppressed verbatim recovery; multi-question "versions" surfaced as I(0)/I(1) not strict/weak); (d) chain to formula recovery for image-math defs. |
| — | 🟠 | **Small trailing `$$` leak** in the AR(p) formal-statement render. |

### Reference

- Spec: `docs/superpowers/specs/2026-06-16-tutor-definition-recovery-design.md`

### Note — convergence with A2-GAP

Items **A2-GAP** and **A3-DR-5 + DR-8(c)** are the same work: *"make verbatim strict/weak/unit-root definition boxes actually render."* It is the single highest-priority open piece of feature work.

### Next action

1. DR-8(c) first — force the gap-concept set to include strict/weak/covariance forms even when `_has_labelled_def` is true (defeats the prose-present suppression).
2. DR-5 — add a frontend structured-render block for `formal_statements[]` (verbatim box + label + source).
3. Fix the trailing `$$` leak in the same pass.

---

## A4. Facilitate story remake

| Field | Value |
|---|---|
| **Status** | ✅ COMPLETE on branch `feat/facilitate-story-remake` (2026-06-12); docs/modal lockstep done. |
| **Mechanism** | One-section narrative pipeline + `ConceptChat` side panel (`/api/concept/explore`). |
| **Remaining** | Live-verify on :5175 + merge to `feat/component-equation-enforcement`. |

### References

- Spec: `docs/superpowers/specs/2026-06-12-facilitate-story-remake-design.md`
- Doc: `docs/services/chat-features/53-facilitate-concept-map.md`

### Next action

Run the live-verify pass on :5175 (concept-map panel end-to-end), then merge `feat/facilitate-story-remake` into `feat/component-equation-enforcement`.

---

## A5. INCIDENT 2026-06-17 — `git reset --hard` data loss

| Field | Value |
|---|---|
| **Status** | 🟡 RECOVERED (recovery commit `d416c16`); hardened as CLAUDE.md **rule 0** + a memory entry. |
| **What happened** | An Ollama implementer dispatched with `--dangerously-skip-permissions` ran `git reset --hard` and wiped uncommitted main work. |
| **Hardening** | Rule 0 (dispatch isolation): commit a WIP recovery point OR dispatch into a dedicated git worktree; never the live primary checkout. Forbid destructive git in delegated agents. |
| **Remaining** | Verify `src/services/chat/agents/deep_tutor.py` is the intended post-recovery state. |

### Next action

Diff `deep_tutor.py` against the pre-incident HEAD + the recovery commit to confirm no silent loss remains.

---

# PART B — Operating-contract migration

The operating contract now mandates **Rule Zero-Zero** (the orchestrator never executes — always dispatch to OpenCode + ollama-cloud): executors run on `ollama-cloud/glm-5.2`, advisors on `ollama-cloud/deepseek-v4-pro`, and the roster uses the `iohan-powers-*` agent names. The items below reconcile the rest of the repo with that contract.

## B1. ✅ Fix the live-verify port in the CLAUDE.md contract

| Field | Value |
|---|---|
| **Status** | ✅ DONE (2026-06-28) — `:8080` → `:5175` corrected in CLAUDE.md rule 2. |
| **Problem** | Rule 2 said "live-verify on :8080". `:8080` belongs to the unrelated **mindmap-caddy** container. |
| **Correct value** | This repo's dev URL is **:5175** (prod `:5173` / backend `:8765`, dev backend `:8766`). |
| **Fix** | Corrected `:8080` → `:5175` in the contract text (governance-file edit). |

---

## B2. ⬜ Rewrite the `feature_Agent` and `system_Agent` shortcuts in CLAUDE.md

| Field | Value |
|---|---|
| **Status** | ⬜ Not started. |
| **Problem** | They currently say *"read `docs/common ground/Agents/X.md` and transform yourself into it"* — i.e. Claude **becomes** an implementer that edits code. That is a direct breach of Rule Zero-Zero. |
| **Fix** | Convert them into **dispatch templates**: the orchestrator stays the orchestrator and dispatches fresh `ollama-cloud/glm-5.2` executors in a worktree. |

### Next action

Rewrite both shortcuts as dispatch templates (worktree + glm-5.2 executor + reviewer), removing the "transform yourself" language.

---

## B3. ⬜ Reconcile the `orchestrator_Agent` / `creative_Advisor` / `debug_Advisor` shortcuts

| Field | Value |
|---|---|
| **Status** | ⬜ Not started. |
| **Problem** | Shortcuts still use old names; advisors not pinned to deepseek-v4-pro; `technical_Advisor` is named in the contract but has **no shortcut**. |
| **Fix** | Rename to `iohan-powers-orchestrator`, `iohan-powers-creative-advisor`, `iohan-powers-debug-advisor`; pin advisors to `ollama-cloud/deepseek-v4-pro`; **add** `iohan-powers-technical-advisor`. |

### Next action

Update the three existing shortcuts and add the missing `technical_Advisor` shortcut.

---

## B4. 🟠 BLOCKING AMBIGUITY — needs a user decision before B2/B3/B5 land

| Field | Value |
|---|---|
| **Status** | 🟠 Blocking. |
| **Conflict** | Rule 3 says all non-orchestrator agents are delegated to ollama-cloud via OpenCode — **NOT Claude subagents**. Yet rules 1-3 name `iohan-powers-*` agents which **ARE** Claude subagents in the registry. |
| **Decision needed** | Are the `iohan-powers-*` names: (a) **role labels** whose execution is dispatched to ollama via OpenCode, or (b) **Claude subagents invoked directly**, with ollama dispatch only for the `glm-5.2` executors? |

### Next action

User decides (a) vs (b); document the answer in the contract before proceeding with B2/B3/B5.

---

## B5. ⬜ Reconcile all `docs/common ground/Agents/*.md`

| File | Status |
|---|---|
| `orchestrator_Agent.md` | ⬜ |
| `feature_Agent.md` | ⬜ |
| `system_Agent.md` | ⬜ |
| `creative_Advisor.md` | ⬜ |
| `debug_Advisor.md` | ⬜ |

| Field | Value |
|---|---|
| **Problem** | All five still describe the old regime (`glm-5.1`, "transform yourself", old roster). |
| **After B4, update to** | `glm-5.2` executors, `deepseek-v4-pro` advisors, Rule Zero-Zero, author-only dispatch + orchestrator-runs-gates, timeout/loop-watch protocol. Consider adding `technical_Advisor.md`. |

### Next action

Block on B4 decision, then rewrite all five agent docs in lockstep with the new contract.

---

## B6. ✅ Update memory (orchestrator-allowed, not a code deliverable)

| Field | Value |
|---|---|
| **Status** | ✅ DONE (2026-06-28) — memory body + description + `MEMORY.md` index line updated to glm-5.2 executors / deepseek-v4-pro advisors. |
| **Files** | `~/.claude/projects/-home-iohan-Documents-toolbox-AI-models-RAG/memory/glm51-implementer-model.md` + its `MEMORY.md` index line. |
| **Problem** | They said "always glm-5.1, never qwen" — stale. |
| **Fix** | Roster = `glm-5.2` executors + `deepseek-v4-pro` advisors; added author-only + timeout/loop-watch guidance. |

---

# PART C — Loose ends / housekeeping

## C1. Citation-numbering fix worktree cleanup

| Field | Value |
|---|---|
| **Status** | ⬜ Not started. |
| **Fact** | Citation-numbering fix is already on main (commit `f38441a`). |
| **Action** | Clean up the stale `fix/citation-numbering-isolated` worktree. |

### Next action

`git worktree remove <path-to-fix/citation-numbering-isolated>` once confirmed merged.

---

## C2. Worktree clutter — prune merged ones

There are ~13 git worktrees, most on already-merged branches. Candidates for `git worktree remove`:

- `qa-story-wiki`
- `facilitate-story-remake`
- `extension-*` (all)
- `qa-deepagent*`
- `statrag-html-docs`
- `citation-numbering-isolated`
- (other already-merged branches found via `git worktree list`)

### Next action

`git worktree list` → for each worktree whose branch is merged into `feat/component-equation-enforcement` or `main`, run `git worktree remove <path>` (use `--force` only if you have verified the branch is fully merged and the worktree holds no uncommitted work).

---

# How to use this file

- **Closing items:** edit them here (status → ✅, fill in the merge/commit), then remove the stale rows. Do not re-add closed items to CLAUDE.md.
- **CLAUDE.md** keeps only a one-line pointer to this file (`docs/system/pending.md`).
- **New pending work:** add a new section under the relevant part; never let CLAUDE.md grow a second table.
- **Review order:** A3 (Definition Recovery) is the highest-leverage open feature; B4 is the highest-leverage governance blocker; C is quick housekeeping.