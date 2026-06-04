# Orchestrator-workers harness ablation — baseline (Plan A: L0)

_frozen multi-author sources · judge=gpt-5.4-nano-2026-03-17 · model held constant (nano workers + synth) · quality + context-fidelity_

| level | question | overall | faith | coverage | synthesis | coherence | fidelity | out_tok | ms | USD |
|---|---|---|---|---|---|---|---|---|---|---|
| L0 | Q0 | 2.25 | 2.0 | 3.0 | 2.0 | 2.0 | 2.0 | 2561 | 28042 | $0.0010 |
| L0 | Q1 | 3.5 | 3.0 | 4.0 | 3.0 | 4.0 | 3.0 | 2907 | 30562 | $0.0012 |
| L0 | Q2 | 3.0 | 3.0 | 3.0 | 2.0 | 4.0 | 3.0 | 2644 | 30056 | $0.0011 |
| L2 | Q0 | 2.0 | 2.0 | 2.0 | 2.0 | 2.0 | 1.0 | 2573 | 26888 | $0.0010 |
| L2 | Q1 | 4.25 | 4.0 | 5.0 | 4.0 | 4.0 | 4.0 | 2816 | 38992 | $0.0011 |
| L2 | Q2 | 2.5 | 2.0 | 2.0 | 2.0 | 4.0 | 3.0 | 2733 | 28888 | $0.0011 |
| L3 | Q0 | 3.5 | 3.0 | 3.0 | 4.0 | 4.0 | 1.0 | 1491 | 25295 | $0.0006 |
| L3 | Q1 | 4.0 | 4.0 | 4.0 | 4.0 | 4.0 | 2.0 | 1338 | 16535 | $0.0005 |
| L3 | Q2 | 2.5 | 2.0 | 3.0 | 2.0 | 3.0 | 3.0 | 1318 | 16050 | $0.0005 |

## Questions

- Q0: Compare how different authors define and motivate the bias-variance tradeoff.
- Q1: Contrast OLS and maximum likelihood estimation across the textbooks.
- Q2: Compare frequentist and Bayesian treatments of estimation.

## Opus verdict — Plan B 3-way A/B (re-baselined, scoped sources)

**Averages (3 questions, 1 run, nano model + judge held constant):**

| level | quality (overall) | fidelity | answer size (out_tok) |
|---|---|---|---|
| L0 flat string | **2.92** | **2.67** | ~2700 |
| L2 structured JSON | **2.92** | **2.67** | ~2700 |
| L3 deepagents synth | **3.33** | **2.0** | ~1380 |

**Structure effect (L2 − L0) ≈ 0.** Handing the synthesizer the briefs as a JSON block
instead of a flattened string changed quality and fidelity by **nothing** on average
(per-question it wobbled both ways — Q1 +0.75, Q0/Q2 −0.25/−0.5, i.e. noise). The
structured handoff is free and harmless but **does not earn a default flip**. The
"context handling" weakness is not the string format.

**deepagents effect (L3 − L2) = +0.41 quality but −0.67 fidelity.** The deepagents
synthesizer produced **higher-rated but much shorter** answers (~1380 vs ~2700 out_tok)
that **retained fewer worker-brief facts** (fidelity 2.0 vs 2.67). So deepagents traded
**breadth/source-retention for tighter, better-reasoned prose** — not obviously a win
for a *grounded* tutor where covering the authors' facts matters. The synthesis/coherence
sub-scores drove the quality bump; faithfulness was flat-to-down.

**Why this is NOT enough to ship deepagents:**
1. **Tiny, noisy sample** — 3 questions, 1 run; Q1 carried every level, Q0/Q2 were weak
   across the board. The +0.41 is inside the run-to-run variance we saw all session.
2. **L3 cost/latency are unreliable** — the eval counts only the final answer length;
   the deepagents agent's internal tool-call turns (read_file ×N, planning) are
   **uncaptured**, so L3's "$0.0005 / 16–25 s" is a **floor, not the real cost**. The
   real L3 cost is higher than L0, not lower.
3. **L3 is free-text only** — no `DeepTutorAnswer` schema; shipping it needs schema
   integration + adding `deepagents` to `requirements.txt`.
4. **Fidelity regressed** — the one metric this whole program targets ("context handling
   between models") got *worse* under deepagents here.

**Recommendation: do NOT productionize deepagents on this evidence; keep L0 default.**
The structured handoff (L2) is a no-op — leave it flag-available but off. If deepagents
is worth another look, it needs: (a) a bigger multi-run question set, (b) real L3 token
capture (instrument the deepagents callbacks / LangSmith), and (c) a look at *why* it
drops brief facts (likely it doesn't read every `/briefs/*.md`). Level 4 (full
subagent-per-author) is **not** justified — L3 already underwhelmed on fidelity.

**Feasibility (from the spike) stands:** deepagents runs on our stack and drives nano;
the blocker is value, not feasibility. Net program takeaway: the orchestrator-workers
context-handling weakness is **not** fixed by reformatting the handoff or by a deepagents
agent — it likely lives upstream (retrieval pulling thin/mixed authors; workers
summarising lossily). The next pilot should target *that*, not more synthesizer harness.

---

_Run notes: scoped books (hansen/wooldridge/stock_watson/gujarati/baltagi/pesaran/islp/
murphy), 5–8 authors/question · content-bearing fidelity · model = nano everywhere ·
L3 = deepagents 0.6.8 StoreBackend synth (real run after fixing an api_key passthrough;
the first run silently fell back to L0 on missing credentials). deepagents uninstalled
post-run (no win); not added to requirements.txt._
