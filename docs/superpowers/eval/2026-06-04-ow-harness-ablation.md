# Orchestrator-workers harness ablation — L0/L2/L3 (corrected fidelity metric)

_frozen multi-author sources · judge=gpt-5.4-nano-2026-03-17 · model held constant (nano workers + synth) · quality + context-fidelity_

| level | question | overall | faith | coverage | synthesis | coherence | fidelity | out_tok | ms | USD |
|---|---|---|---|---|---|---|---|---|---|---|
| L0 | Q0 | 3.75 | 3.0 | 5.0 | 3.0 | 4.0 | 5.0 | 2561 | 28042 | $0.0010 |
| L0 | Q1 | 4.25 | 4.0 | 5.0 | 4.0 | 4.0 | 5.0 | 2907 | 30562 | $0.0012 |
| L0 | Q2 | 3.75 | 3.0 | 5.0 | 3.0 | 4.0 | 4.0 | 2644 | 30056 | $0.0011 |
| L2 | Q0 | 3.75 | 3.0 | 5.0 | 3.0 | 4.0 | 5.0 | 2573 | 26888 | $0.0010 |
| L2 | Q1 | 4.5 | 4.0 | 5.0 | 4.0 | 5.0 | 5.0 | 2816 | 38992 | $0.0011 |
| L2 | Q2 | 4.0 | 3.0 | 5.0 | 4.0 | 4.0 | 4.0 | 2733 | 28888 | $0.0011 |
| L3 | Q0 | 4.25 | 4.0 | 4.0 | 4.0 | 5.0 | 5.0 | 1491 | 25295 | $0.0006 |
| L3 | Q1 | 4.5 | 4.0 | 5.0 | 4.0 | 5.0 | 5.0 | 1338 | 16535 | $0.0005 |
| L3 | Q2 | 4.0 | 3.0 | 4.0 | 4.0 | 5.0 | 4.0 | 1318 | 16050 | $0.0005 |

## Questions

- Q0: Compare how different authors define and motivate the bias-variance tradeoff.
- Q1: Contrast OLS and maximum likelihood estimation across the textbooks.
- Q2: Compare frequentist and Bayesian treatments of estimation.

## Verdict — the fidelity problem was a measurement bug (root-caused + fixed)

**Root cause (systematic debugging).** The fidelity judge truncated its inputs:
`briefs[:2500]` and `answer[:3000]` (quality judge: `answer[:4000]`). With the scoped
multi-author setup the briefs run **9–12k chars (5–8 authors)** and answers **6–12k
chars**, so the judge saw only **~1.5 authors of briefs** and **~30–50% of the answer**,
then was asked "did the brief facts survive?" — facts that survived into the unseen
remainder were scored as **dropped**. Minimal test (re-judge identical stored rows,
truncated vs full): L0 Q0 2.0→**5.0**, L3 Q0 1.0→**5.0**, L0 Q1 3.0→**5.0**. Root cause
confirmed: **measurement artifact, not context loss.** This truncation was present since
Plan A, so the original "fidelity 1–2 / context-handling weakness" that motivated this
whole ablation was **never real**.

**Fix.** `_JUDGE_CHARS = 12000` (full briefs + full answer to both judges), guard test
`test_fidelity_input_not_truncated`. Re-judged the stored answers (no workflow re-run).

**Corrected results (3 questions, 1 run, nano fixed):**

| level | quality avg | fidelity avg | out_tok |
|---|---|---|---|
| L0 flat string | 3.92 | **4.67** | ~2700 |
| L2 structured | 4.08 | **4.67** | ~2700 |
| L3 deepagents | 4.25 | **4.67** | ~1380 |

**Conclusions (reversing the earlier, truncated verdict):**
1. **No fidelity problem exists.** Every level retains worker-brief facts at ~4.67/5.
   The orchestrator-workers synthesizer is faithful; there is nothing to "fix" here.
2. **The earlier "L3 −0.67 fidelity" is retracted** — it was truncation misaligning the
   visible answer window (L3 leads with different authors) against the visible brief
   window. With full text L3 fidelity = L0 = L2.
3. **Levels are close on quality** (L0 3.92 → L2 4.08 → L3 4.25), a monotone but small
   rise inside the 3-question/1-run noise. L3 reaches it with **shorter** answers
   (~1380 vs ~2700 out_tok) — tighter prose, equal fidelity. Still: L3 cost is
   understated (uncaptured deepagents tool-call turns) and it is free-text only.
4. **Recommendation unchanged on shipping, changed on reasoning:** keep L0 default; do
   not adopt deepagents on a 3q/1-run +0.33 quality edge. But the *program premise* is
   corrected — the next pilot should NOT chase a non-existent OW context-handling
   weakness. The real lesson is methodological: **validate the metric before trusting
   the result** (truncation caps quietly invalidated three eval runs).

**Feasibility (spike) stands;** deepagents runs on our stack. The blocker remains value,
now even weaker since the fidelity gap it was meant to close did not exist.

---

_Run notes: scoped books, 5–8 authors/q · model = nano everywhere · fidelity+quality
judges fixed to full-text (`_JUDGE_CHARS=12000`) · L3 = deepagents 0.6.8 (uninstalled
post-run) · single-run judge retains mild variance — multi-run averaging is a cheap
future hardening._
