# Plan C — powered deepagents synthesizer comparison (4 arms)

_6 questions x 3 runs · full-text judge=gpt-5.4-nano-2026-03-17 · nano fixed · real token capture (main+subagents+tools)_

| arm | question | overall (mean ± range) | fidelity | in_tok | out_tok | ms | USD | ok |
|---|---|---|---|---|---|---|---|---|
| L0 | Q0 | 3.58 ±[3.5–3.75] | 4.0 | 0 | 2445 | 49489 | $0.0010 | 3/3 |
| L0 | Q1 | 4.25 ±[4.0–4.5] | 3.67 | 0 | 2894 | 50572 | $0.0012 | 3/3 |
| L0 | Q2 | 4.08 ±[3.75–4.5] | 4.0 | 0 | 2786 | 43400 | $0.0011 | 3/3 |
| L0 | Q3 | 3.83 ±[3.5–4.25] | 3.0 | 0 | 2756 | 43279 | $0.0011 | 3/3 |
| L0 | Q4 | 4.17 ±[4.0–4.5] | 2.67 | 0 | 2543 | 57662 | $0.0010 | 3/3 |
| L0 | Q5 | 3.83 ±[3.5–4.25] | 3.0 | 0 | 2625 | 47732 | $0.0011 | 3/3 |
| L3a | Q0 | 3.25 ±[1.75–4.5] | 2.67 | 0 | 1062 | 33115 | $0.0004 | 3/3 |
| L3a | Q1 | 4.5 ±[4.5–4.5] | 4.33 | 0 | 1421 | 34191 | $0.0006 | 3/3 |
| L3a | Q2 | 4.5 ±[4.5–4.5] | 4.67 | 0 | 1251 | 25256 | $0.0005 | 3/3 |
| L3a | Q3 | 3.83 ±[3.5–4.0] | 4.0 | 0 | 916 | 21232 | $0.0004 | 3/3 |
| L3a | Q4 | 4.5 ±[4.5–4.5] | 4.0 | 0 | 1306 | 32999 | $0.0005 | 3/3 |
| L3a | Q5 | 4.42 ±[4.25–4.5] | 4.0 | 0 | 1268 | 30829 | $0.0005 | 3/3 |
| L3b | Q0 | 4.5 ±[4.5–4.5] | 4.33 | 65071 | 2727 | 56959 | $0.0076 | 3/3 |
| L3b | Q1 | 4.58 ±[4.5–4.75] | 5.0 | 35255 | 2345 | 41373 | $0.0045 | 3/3 |
| L3b | Q2 | 4.42 ±[4.25–4.5] | 4.33 | 35801 | 1452 | 34978 | $0.0042 | 3/3 |
| L3b | Q3 | 4.08 ±[3.5–4.5] | 4.0 | 41204 | 1609 | 32509 | $0.0048 | 3/3 |
| L3b | Q4 | 4.5 ±[4.5–4.5] | 5.0 | 26459 | 1276 | 32624 | $0.0032 | 3/3 |
| L3b | Q5 | 4.25 ±[4.25–4.25] | 4.33 | 25774 | 1259 | 28653 | $0.0031 | 3/3 |
| L4 | Q0 | 4.5 ±[4.25–4.75] | 5.0 | 65754 | 5619 | 43344 | $0.0088 | 3/3 |
| L4 | Q1 | 4.08 ±[3.75–4.5] | 4.33 | 98480 | 5786 | 47501 | $0.0122 | 3/3 |
| L4 | Q2 | 4.58 ±[4.5–4.75] | 4.33 | 44950 | 3364 | 47414 | $0.0058 | 3/3 |
| L4 | Q3 | 4.25 ±[4.25–4.25] | 3.33 | 42140 | 4022 | 84985 | $0.0058 | 3/3 |
| L4 | Q4 | 4.58 ±[4.5–4.75] | 4.33 | 56137 | 3866 | 43999 | $0.0072 | 3/3 |
| L4 | Q5 | 4.25 ±[4.25–4.25] | 4.0 | 42258 | 2950 | 71893 | $0.0054 | 3/3 |

## Questions

- Q0: Compare how different authors define and motivate the bias-variance tradeoff.
- Q1: Contrast OLS and maximum likelihood estimation across the textbooks.
- Q2: Compare frequentist and Bayesian treatments of estimation.
- Q3: Compare how the textbooks treat heteroskedasticity and its remedies.
- Q4: Contrast hypothesis testing and confidence intervals across the authors.
- Q5: Compare the treatments of omitted variable bias and endogeneity.

## Opus verdict — the harness + skill wins; subagents over-engineer it

**Grand means across 6 questions × 3 runs (nano fixed everywhere, full-text judge):**

| arm | quality | fidelity | real USD/answer | beats L0 on |
|---|---|---|---|---|
| L0 baseline (current synth) | 3.96 | 3.39 | ~$0.0011* | — |
| L3a bare deepagents | 4.17 | 3.95 | **$0.0005** | 4/6 (loses Q0) |
| **L3b deepagents + written skill** | **4.39** | **4.50** | $0.0046 | **6/6** |
| L4 deepagents + subagents-per-author | 4.37 | 4.22 | $0.0075 | 5/6 |

\* L0 USD is estimated (`out_tok = len/4`, production synth streams without usage); the
deepagents arms (L3a/L3b/L4) use **real** callback tokens (main + subagents + tool turns).

**Applying the decision rule (mean − L0 > spread, fidelity not regressing, consistent):**

- **L3b (deepagents + the written synthesis skill) PASSES — clear, consistent win.**
  +0.43 quality over L0, beating it on **all 6 questions** (not one regression), and
  **+1.11 fidelity** (4.50 vs 3.39). The per-question ranges are tight (mostly ±0.0–0.25),
  so the gap clears the spread. The **skill is the active ingredient**: L3b beats bare
  L3a by +0.22 quality and +0.55 fidelity — a written `SKILL.md` telling the agent to read
  every brief, retain every key point, and compare explicitly is what closes the gap.
- **L4 (subagents-per-author) does NOT pay off.** It is *worse* than L3b on both quality
  (4.37) and fidelity (4.22) while costing **1.6× L3b and ~7× L0** ($0.0075) and showing
  the highest latency/variance. Delegating per-author analysis to subagents adds tokens
  and coordination overhead without beating the single skilled agent. **Reject L4.**
- **L3a (bare deepagents) is the cost surprise:** *cheaper than L0* ($0.0005 vs ~$0.0011)
  with a modest quality bump — but inconsistent (one Q0 run scored 1.75; range [1.75–4.5]),
  so not trustworthy alone.

**This answers the two challenges that launched Plan C:**
1. *"Why not adopt if the average increases?"* — With proper power (3 runs, 6 questions,
   spread shown) the increase is **real and consistent for L3b**, not noise. The earlier
   "don't adopt" was right *for bare deepagents on 3q/1run*, wrong as a blanket call.
2. *"Compared with skills + subagents?"* — Yes, now measured: **skills help a lot,
   subagents hurt.** The prior Plan B tested only the weakest config (bare) and undersold
   the harness.

**Recommendation: adopt L3b (deepagents + synthesis skill) as a real candidate**, behind
the flag, for the orchestrator-workers synthesizer — it consistently beats the current
synth on quality and faithfulness at a still-tiny absolute cost (~$0.0046/answer, 4× L0).
**Reject L4.** Before shipping it needs a productionization plan: (a) integrate the
free-text output into the `DeepTutorAnswer` schema, (b) add `deepagents` to
`requirements.txt`, (c) confirm latency (L3b ~30–57 s) is acceptable for the synth stage
or gate it. That is Plan D.

**Caveats:** nano judge has residual ±0.25 variance (mitigated by 3-run averaging + ranges
shown); L0's cost is an estimate so the L3b-vs-L0 *cost* multiple is approximate (the
deepagents arms' costs are real); 6 questions is powered but not huge.

---

_Run notes: 72/72 ok (4 arms × 6 q × 3 runs) after a sem=10 → sem=3 → sem=2+retry
de-escalation to clear OpenAI 429s (L4's subagent fan-out was the rate-limit driver);
real token capture via `UsageMetadataCallbackHandler`; deepagents 0.6.8 (uninstalled
post-run; not added to requirements.txt — Plan D handles that if L3b ships)._
