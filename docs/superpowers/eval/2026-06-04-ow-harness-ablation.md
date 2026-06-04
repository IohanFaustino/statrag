# Orchestrator-workers harness ablation — baseline (Plan A: L0)

_frozen multi-author sources · judge=gpt-5.4-nano-2026-03-17 · model held constant (nano workers + synth) · quality + context-fidelity_

| level | question | overall | faith | coverage | synthesis | coherence | fidelity | out_tok | ms | USD |
|---|---|---|---|---|---|---|---|---|---|---|
| L0 | Q0 | 3.0 | 2.0 | 3.0 | 3.0 | 4.0 | 2.0 | 2456 | 29792 | $0.0010 |
| L0 | Q1 | 2.5 | 2.0 | 3.0 | 2.0 | 3.0 | 2.0 | 2606 | 32660 | $0.0010 |
| L0 | Q2 | 3.25 | 3.0 | 3.0 | 3.0 | 4.0 | 1.0 | 2878 | 40231 | $0.0012 |

## Questions

- Q0: Compare how different authors define and motivate the bias-variance tradeoff.
- Q1: Contrast OLS and maximum likelihood estimation across the textbooks.
- Q2: Compare frequentist and Bayesian treatments of estimation.

## Opus verdict + feasibility note

**deepagents feasibility: `FEASIBLE`** (spike `docs/superpowers/eval/_spike/deepagents-findings.md`).
deepagents 0.6.8 imports, drives our nano model via `ChatOpenAI`, and its **virtual
filesystem** (`files` in agent state) works — the exact worker→synthesizer channel L2
needs. langchain/langgraph took minor in-pin bumps; suite stayed green (641 passed).
**Plan B (L2/L3) is greenlit.**

**L0 baseline (model held constant, nano):** quality is **mediocre** — overall
3.0 / 2.5 / 3.25, with **faithfulness low (2.0)** and **context-fidelity low
(2.0 / 2.0 / 1.0)**. Synthesis (the actual author-comparison) sat at 2–3. Latency is
heavy (30–40 s) because the workflow fans out one worker per author over up to 10
authors. So there is real headroom for a better handoff to improve on.

**Honest caveat — the baseline is partly confounded by retrieval, not just the
handoff.** The briefs reveal that `top_k=10` over **all books** pulled **off-topic
authors** (Rothman, Auffarth — RAG/DL-ops texts) whose briefs literally say *"the
provided source does not discuss this."* A synthesizer *should* drop those no-info
briefs, so the low fidelity score is **partly correct behavior**, not pure context
loss. The current fidelity metric counts dropped no-info briefs against the answer,
which is unfair. Two things this surfaced:
1. **Scope retrieval** for the ablation to the relevant stats/econ books, so workers
   aren't spawned on irrelevant authors (wasted calls + confounded metric).
2. **Refine the fidelity metric** to score retention only over **content-bearing**
   briefs (ignore "no-info" briefs).

**What L0 cleanly establishes:** the harness scaffold (flag + L1 tracing passthrough +
`on_briefs` hook) works and is behavior-identical; the eval pipeline (freeze → run →
judge) runs end-to-end; and we have numbers L2/L3 must beat — but those numbers should
be **re-baselined on scoped sources + the refined fidelity metric** before trusting the
delta.

**Recommendation / next step (Plan B).** Proceed with deepagents, but first land two
small fixes in the eval (scope `BOOKS` to relevant slugs; fidelity over content-bearing
briefs only), re-run the L0 baseline, then build **L2** (synthesizer reads per-author
brief *files* from the deepagents virtual FS instead of `_format_author_briefs`) and
A/B it. L3 (subagent-per-author) only if L2 wins. Keep the model fixed at nano so the
delta is the harness, per the design.
