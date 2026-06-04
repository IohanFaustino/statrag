# Planner-chain model comparison — decompose→expand→consolidate

_contestants run the 3-step chain (baseline = single-call nano) · judge=gpt-5.4-nano-2026-03-17 · 3 questions · plan-quality only_

| contestant | question | overall | decomp | coverage | targeting | redundancy | out_tok | ms | USD |
|---|---|---|---|---|---|---|---|---|---|
| single-call(nano) baseline | Q0 | 4.25 | 4.0 | 4.0 | 4.0 | 5.0 | 213 | 3105 | $0.0000 |
| single-call(nano) baseline | Q1 | 4.5 | 5.0 | 5.0 | 4.0 | 4.0 | 260 | 2429 | $0.0000 |
| single-call(nano) baseline | Q2 | 4.75 | 4.0 | 5.0 | 5.0 | 5.0 | 308 | 3108 | $0.0000 |
| gemini-chain | Q0 | FAILED |  |  |  |  | 366 | 12724 | _JSONDecodeError: Expecting property name enclosed in double quotes: line 5 column 5 (char 69)_ |
| gemini-chain | Q1 | FAILED |  |  |  |  | 372 | 6591 | _JSONDecodeError: Expecting property name enclosed in double quotes: line 23 column 55 (char 1262)_ |
| gemini-chain | Q2 | FAILED |  |  |  |  | 272 | 7457 | _JSONDecodeError: Unterminated string starting at: line 12 column 16 (char 624)_ |
| nano-chain | Q0 | 4.75 | 5.0 | 4.0 | 5.0 | 5.0 | 535 | 6960 | $0.0003 |
| nano-chain | Q1 | 4.25 | 4.0 | 5.0 | 4.0 | 4.0 | 879 | 8371 | $0.0005 |
| nano-chain | Q2 | 4.75 | 5.0 | 5.0 | 5.0 | 4.0 | 1142 | 8844 | $0.0006 |
| qwen-chain | Q0 | 4.0 | 4.0 | 5.0 | 4.0 | 3.0 | 479 | 13031 | $0.0011 |
| qwen-chain | Q1 | 4.25 | 4.0 | 4.0 | 5.0 | 4.0 | 824 | 18745 | $0.0016 |
| qwen-chain | Q2 | 4.5 | 4.0 | 5.0 | 4.0 | 5.0 | 839 | 19372 | $0.0016 |

## Questions

- Q0: State the bias of an unbiased estimator.
- Q1: What are the components of a time series?
- Q2: Compare L1 and L2 regularization.

## Plan dumps

### single-call(nano) baseline — Q0

```
concepts: ['unbiased estimator', 'bias']
perspectives: 1
facets:
- definition of bias of an estimator
- unbiasedness condition (E[estimator] = parameter) implies zero bias
- real-world application or empirical case of the bias concept (e.g., bias check in a Monte Carlo simulation or sample estimator)
- related framings: other error decompositions involving bias (e.g., mean squared error decomposition)
queries:
- definition and formula for the bias of an estimator
- unbiased estimator condition E[\hat{\theta}] = \theta and proof that bias is zero
- worked example or Monte Carlo simulation demonstrating bias of an estimator and verifying unbiasedness
- mean squared error decomposition into variance and squared bias (bias-variance/MSE decomposition)
- bias concept in the context of estimator performance measures (MSE, risk) and how bias affects them
```

### single-call(nano) baseline — Q1

```
concepts: ['time series components', 'trend', 'seasonality']
perspectives: 2
facets:
- trend component definition and typical modeling forms
- seasonal component definition and typical modeling forms
- cyclical component definition and distinction from seasonality
- irregular (remainder) component definition
- real-world application or empirical case of time series decomposition (e.g., forecasting sales with trend/seasonality)
- related framings such as classical decomposition vs STL/ETS and connections to ARIMA/structural time series
queries:
- classical time series decomposition components: trend, seasonal, cyclical, irregular (remainder) definitions
- trend component modeling in time series decomposition (additive vs multiplicative, polynomial/smoothing trend)
- seasonal component modeling in time series decomposition (additive vs multiplicative, seasonal indices)
- cyclical vs seasonal components in time series (definitions, periodicity assumptions) and irregular component
- worked example applying time series decomposition to forecasting (trend + seasonality + irregular) and comparison to alternative methods like STL/ETS or ARIMA/structural time series
```

### single-call(nano) baseline — Q2

```
concepts: ['L1 regularization', 'L2 regularization', 'regularization']
perspectives: 4
facets:
- L1 regularization objective and penalty term (L1 norm)
- L2 regularization objective and penalty term (L2 norm)
- optimization/geometry comparison (sparsity via L1, shrinkage via L2; subgradient vs gradient)
- real-world application or empirical case comparing L1 vs L2 (e.g., feature selection in high-dimensional regression)
- related framings (MAP interpretation with Laplace vs Gaussian priors; connections to ridge vs lasso and elastic net)
queries:
- L1 regularization (lasso) objective function with L1 norm penalty and its optimization conditions (subgradient)
- L2 regularization (ridge) objective function with L2 norm penalty and its optimization conditions (gradient/closed-form in linear regression)
- geometric interpretation of L1 vs L2 regularization (constraint sets, sparsity of L1, shrinkage of L2) and implications for coefficient paths
- worked empirical example comparing lasso (L1) and ridge (L2) in high-dimensional regression with feature selection or prediction performance
- Bayesian/MAP interpretation of L1 vs L2 regularization (Laplace vs Gaussian priors) and connections to ridge, lasso, and elastic net
```

### gemini-chain — Q0

```

```

### gemini-chain — Q1

```

```

### gemini-chain — Q2

```

```

### nano-chain — Q0

```
sub_questions:
- What is the definition and formula for the bias of an estimator?
- What condition makes an estimator unbiased (in terms of expectation)?
- What is a worked example of an unbiased estimator and how its bias is verified?
concepts: ['Estimator bias', 'Unbiased estimator (expectation condition)', 'Bias verification via worked example']
perspectives: 2
facets:
- Bias definition and mathematical formula (Bias(\hat{\theta}) = E[\hat{\theta}] - \theta)
- Unbiasedness condition expressed using expectation (E[\hat{\theta}] = \theta)
- Worked example estimator with step-by-step verification that bias equals zero
queries:
- Provide the definition of estimator bias and the formula Bias(\hat{\theta}) = E[\hat{\theta}] - \theta, including notation for parameter \theta and estimator \hat{\theta].
- State the condition for an estimator to be unbiased in terms of expectation, i.e., E[\hat{\theta}] = \theta, and explain what expectation is taken over.
- Find a worked example of an unbiased estimator and show the verification steps by computing E[\hat{\theta}] and demonstrating it equals the target parameter (thereby bias = 0).
```

### nano-chain — Q1

```
sub_questions:
- What are the standard components of a time series (e.g., trend, seasonality, cyclical, irregular) and what does each represent?
- How is the trend component defined and interpreted in a time series?
- How is seasonality defined and how does it differ from cyclical variation?
- What is an application case where decomposing a time series into components is used (e.g., forecasting demand or sales)?
- In what related frameworks is time-series decomposition used beyond basic forecasting (e.g., classical decomposition vs. STL, state-space models)?
concepts: ['time series components (trend, seasonality, cyclical, irregular)', 'time series decomposition for forecasting and analysis', 'decomposition methods (classical, STL, state-space)']
perspectives: 2
facets:
- List standard time series components (trend, seasonality, cyclical, irregular) and define what each represents
- Define and interpret the trend component (direction and magnitude over time)
- Define seasonality and contrast it with cyclical variation (fixed vs variable period/regularity)
- Provide a concrete application case of decomposition for forecasting demand/sales and explain how components inform forecasts
- Identify related decomposition frameworks/methods (classical decomposition, STL, state-space) and how decomposition is used in each
queries:
- textbook definition of time series components: trend, seasonality, cyclical, irregular; what each component represents
- definition of trend component in time series interpretation: long-term movement; how to interpret direction and magnitude over time
- time series seasonality definition (fixed periodic pattern) vs cyclical variation definition (variable period/regularity); key differences
- application of time series decomposition for forecasting demand or sales: how trend/seasonality/irregular components inform forecasts
- comparison of time series decomposition methods: classical decomposition vs STL vs state-space models; how each models trend/seasonality/irregular
```

### nano-chain — Q2

```
sub_questions:
- What are the definitions of L1 and L2 regularization terms in an objective function?
- How do L1 and L2 regularization differ in their effects on coefficient sparsity (feature selection) and shrinkage?
- How do L1 and L2 regularization differ in their geometric interpretation (constraint/penalty shapes) and resulting optimization behavior?
- What is a worked applied example (e.g., linear regression or logistic regression) showing when L1 vs L2 regularization performs better?
- In what related settings do L1 and L2 regularization appear (e.g., LASSO vs ridge, elastic net, Bayesian priors)?
concepts: ['L1 regularization (LASSO)', 'L2 regularization (ridge)', 'Geometric and Bayesian interpretations of L1 vs L2']
perspectives: 4
facets:
- Mathematical definitions: how L1 and L2 penalties are written and added to the objective (||w||_1, ||w||_2 with strength λ)
- Effect on sparsity and shrinkage: L1 tends to yield exact zeros (feature selection) vs L2 mainly shrinks without exact zeros
- Geometric interpretation: L1 vs L2 constraint/penalty geometry (diamond vs sphere) and optimization behavior (corner vs smooth solutions)
- Worked applied example: when L1 vs L2 performs better (sparse true coefficients vs dense/collinear signals) in linear/logistic regression
- Related settings and mappings: LASSO, ridge, elastic net, and Bayesian priors (Laplace for L1, Gaussian for L2)
queries:
- definition of L1 regularization term in objective function: add λ * ||w||_1 (sum of absolute values of coefficients) to the loss
- compare L1 vs L2 regularization effects on sparsity and shrinkage: LASSO produces sparse coefficients (exact zeros) while ridge shrinks coefficients without exact zeros
- geometric interpretation of L1 and L2 regularization constraint sets: L1 ball (diamond) vs L2 ball (sphere) and how corners vs smooth boundaries lead to different optimization solutions
- worked example comparing LASSO and ridge regression on synthetic data: sparse true coefficients vs dense/collinear coefficients; summarize when L1 outperforms L2 and vice versa
- relationships between L1 and L2 regularization and related methods: LASSO, ridge, elastic net; Bayesian interpretation with Laplace prior for L1 and Gaussian prior for L2
```

### qwen-chain — Q0

```
sub_questions:
- What is the definition and formula for the bias of an estimator?
- What condition makes an estimator unbiased?
- What is a real case where estimator bias matters in practice?
- In what other settings does estimator bias arise, such as regularization or shrinkage?
concepts: ['bias of an estimator', 'unbiased estimator', 'bias–variance tradeoff']
perspectives: 3
facets:
- formal definition + formula involving expected value and true parameter
- mathematical condition on expected value equaling true parameter
- concrete applied scenario with consequences of bias
- role and source of bias in regularization and shrinkage methods
- application-case
- related-framings
queries:
- definition and mathematical formula for bias of an estimator in statistics
- condition for an estimator to be unbiased
- real-world example where estimator bias affects inference or decision-making
- how bias arises in regularized estimators like ridge regression or shrinkage estimators
- how bias of an estimator is framed in relation to variance, consistency, and model selection
```

### qwen-chain — Q1

```
sub_questions:
- What is the definition and mathematical form of the trend component?
- What is the definition and mathematical form of the seasonal component?
- What is the definition and mathematical form of the cyclical component?
- What is a real empirical example where decomposing a time series into its components clarified an economic or business insight?
- In what other statistical or machine learning frameworks do these time series components reappear (e.g., state-space models, STL decomposition, Prophet, or spectral analysis)?
concepts: ['trend component', 'seasonal component', 'cyclical component']
perspectives: 3
facets:
- formal definition + standard functional form (e.g., linear, polynomial, or smooth deterministic function)
- formal definition + standard functional form (e.g., periodic function with fixed period, trigonometric or dummy-variable formulation)
- formal definition + distinction from seasonal component + typical functional form (e.g., non-fixed-period oscillation, often modeled via stochastic cycles)
- specific dataset + decomposition method used + actionable insight uncovered (e.g., policy response, forecasting improvement, anomaly detection)
- named frameworks (e.g., state-space models, STL, Prophet, spectral analysis) + how each represents or estimates the three core components
queries:
- definition and mathematical representation of trend component in time series decomposition
- definition and mathematical representation of seasonal component in time series decomposition
- definition and mathematical representation of cyclical component in time series decomposition
- real-world example of time series decomposition revealing economic or business insight (e.g., retail sales, GDP, unemployment)
- statistical or machine learning frameworks that explicitly model or recover trend, seasonal, and cyclical components
```

### qwen-chain — Q2

```
sub_questions:
- What is the mathematical definition and penalty term for L1 regularization?
- What is the mathematical definition and penalty term for L2 regularization?
- How do L1 and L2 regularization differ in their effect on coefficient estimates (e.g., sparsity vs. shrinkage)?
- What is a real-world application where L1 regularization is preferred over L2, and why?
- In what other statistical or machine learning frameworks do L1 and L2 penalties appear (e.g., Bayesian priors, generalized linear models, deep learning)?
concepts: ['L1 regularization', 'L2 regularization', 'regularization effects']
perspectives: 3
facets:
- penalty term expression and standard notation
- effect on coefficient estimates (sparsity vs. shrinkage) and geometric interpretation
- real-world application domains and rationale for preference
- appearance in other statistical/ML frameworks (e.g., Bayesian priors, GLMs, deep learning)
queries:
- mathematical definition of L1 regularization penalty term in linear regression including ‖β‖₁ notation and λ scaling
- mathematical definition of L2 regularization penalty term in linear regression including ‖β‖₂² notation and λ scaling
- comparison of L1 and L2 regularization effects on coefficient estimates in linear models with emphasis on sparsity induction, uniform shrinkage, and constraint geometry
- real-world application where L1 regularization is preferred over L2, with domain-specific justification such as interpretability or high-dimensional feature selection
- L1 and L2 penalties in Bayesian inference (e.g., Laplace vs. Gaussian priors), generalized linear models, and deep learning (e.g., weight decay, elastic net)
```


## Opus verdict

**Averages (3 questions):** nano-chain **4.58**, single-call(nano) baseline **4.50**,
qwen-chain **4.25**, gemini-chain **FAILED** (all 3).

**The chain barely beats the single call.** nano-chain (4.58) edges the single-call
baseline (4.50) by **+0.08 overall** — inside the noise of a 1-run, nano-judged,
3-question eval. For that sliver the chain costs **3 LLM calls instead of 1**
(~$0.0005 vs ~$0.0001/question, ~3× latency: 7–9 s vs 2–3 s). On this evidence the
decomposition chain does **not** justify becoming the default. Keep
`TUTOR_PLANNER_CHAIN` **off**; it's a quality lever to pull per-question, not a
blanket upgrade.

**Best model for the chain: nano.** Among the three contestants that completed,
nano-chain wins quality (4.58), is cheapest of the working three, and is ~2× faster
than qwen. qwen-chain is reliable and competent (4.25) but **3× nano's cost** and the
**slowest** (13–19 s for 3 sequential calls) — its lower redundancy score (a 3.0 on
Q0) shows it duplicated facets/queries more than nano. So if the chain is enabled,
run it on nano.

**gemini-2.5-flash is unusable here.** It emitted **non-strict JSON** (trailing
commas → `Expecting property name`, plus one mid-string truncation) at the
expand/consolidate steps, failing all three. This is the same malformed-output strike
as the ts-components eval. Consequence beyond the eval: in production the chain with
gemini would parse-fail every time and silently fall back to the single-call planner —
so gemini + chain is pointless. nano and qwen emit clean JSON.

**The eval caught a real production bug.** The first run failed for nano too — the
chain's `_planner_call` capped each step at `max_completion_tokens=300`, which
truncated nano's verbose decompose JSON mid-string (`Unterminated string`). That cap
is **production code**, so the shipped chain would have truncated for nano (its own
default model) on any non-trivial question. Fixed to 700 in this branch (commit on
`feat/planner-chain`); the rerun above is post-fix. Lesson: reasoning models need
generous JSON budgets, and strict `json.loads` makes output-format discipline a
first-class reliability axis.

**Recommendation.** Ship the chain **flag-gated, default off** (as built). If you ever
turn it on, pin it to **nano**. Do not route the chain to gemini. Revisit a default
flip only with a broader, multi-run eval — the +0.08 here is not a mandate.

---

_Run notes: 3 questions (narrow/standard/broad) · judge=nano (fixed) · plain JSON +
`strip_fences` (no `json_schema`) · per-step cap 700, 60 s timeout · gemini failed all
3 on malformed JSON; verdict rests on nano-chain, qwen-chain, single-call baseline._
