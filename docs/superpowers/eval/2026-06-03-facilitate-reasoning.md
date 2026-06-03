# Facilitate map+teach — reasoning/CoT vs none (A/B)

_hansen ch07 §7.2–7.5 · 3 runs/variant · LLM-judge (1–5) · judge=gpt-5.4-nano-2026-03-17_

> **Verdict (2026-06-03):** statistical tie (+0.01 overall). Reasoning lifts
> keypoint_coverage (+0.17) and faithfulness (+0.08) but *worsens* non_expansion
> (−0.16, i.e. longer/padded), and qualitative inspection shows **regressions**
> the score didn't catch. **Recommend: do NOT ship default-ON. Ship OFF behind
> the flag (or iterate the reasoning prompts first).** See Analysis below.

## Analysis

Per-dim delta (reasoning − baseline): clarity 0 · faithfulness +0.08 ·
keypoint_cov +0.17 · non_expansion **−0.16** · concept_id 0 · overall **+0.01**.

The +0.01 is noise. More telling, the reasoning bodies introduce three defects the
baseline mostly avoids — visible in the samples below:

1. **Marker+term leakage.** §7.5 reasoning writes `[[c1]] Weak Law of Large
   Numbers (WLLN)`, `[[c2]] Consistency idea`, `[[c3]] Consistency of $\hat\mu=...$`.
   The rule is to write `[[cN]]` *in place of* the term — baseline obeys it; the
   reasoning variant leaks the term word beside the marker (the pill would render
   doubled).
2. **Placeholder-ish blockquotes.** §7.4 `> **Chebyshev's inequality** the
   definition…`, §7.2 `> **Sequence convergence** the definition of convergence…`,
   §7.5 `> **Consistency** the definition via convergence in probability`. The
   planning step leaks plan-speak ("the definition…") into the real definition box.
   Baseline blockquotes are complete definitions.
3. **Broken LaTeX.** reasoning bodies show `$delta$`, `$ varepsilon>0$`,
   `$ sigma_n^2$` (dropped backslash). The shipped VERIFY stage (skipped in this
   eval) repairs LaTeX, so this one is partly mitigated in production — but it
   signals the reasoning wrapper degrades math hygiene before verify.

The verify stage would fix (3) but not (1) or (2). So as currently prompted,
reasoning trades a tiny coverage gain for longer output + anchor/definition
regressions. Not worth a default-ON ship.

**Options for the user:** (a) ship OFF behind `FACILITATE_REASONING` and revisit;
(b) drop the change; (c) iterate the reasoning prompts to forbid marker+term
adjacency and plan-speak in blockquotes, then re-run this eval before deciding.

| variant | overall | clarity | faithfulness | keypoint_cov | non_expansion | concept_id |
|---|---|---|---|---|---|---|
| baseline | 3.52 | 4.0 | 3.42 | 3.75 | 2.33 | 4.08 |
| reasoning | 3.53 | 4.0 | 3.5 | 3.92 | 2.17 | 4.08 |

**Winner:** reasoning  (reasoning − baseline = +0.01)

## Sample bodies (run 1)

### 7.2 ASYMPTOTIC LIMITS
**baseline:**

Asymptotic analysis matters because it lets you understand what happens “in the long run” without computing everything exactly. By focusing on what a quantity approaches as the sample size grows, you get useful approximations that are often much easier to work with.

The first building block is the limit of a sequence as $n\to\infty$, which formalizes the idea of “approaching” a value. We capture this with the convergence definition: a sequence approaches $a$ when it eventually stays within any chosen tolerance of $a$. This is the core tool behind asymptotic reasoning [[c1]].

Once you have convergence, asymptotic analysis uses it as an approximation device. Instead of interpreting $n\to\infty$ literally, you treat the limit as a guide for how the behavior looks for large but finite $n$. In other words, the limit helps you approximate the original problem [[c2]].

To verify convergence, you use a precise criterion: for every tolerance $\delta>0$, the sequence must get close enough to $a$ and stay close. Concretely, there must exist an index $n_\delta$ such that for all $n\ge n_\delta$, the distance satisfies $|a_n-a|\le \delta$. This “eventually within $\delta$” condition is the convergence criterion [[c3]].

### Example: $a_n=n^{-1}$
Pick any $\delta>0$. If $n\ge 1/\delta$, then $|a_n-0|=n^{-1}\le \delta$, so the definition is satisfied with $a=0$ and $n_\delta=1/\delta$.

### Example: $a_n=n^{-1}(-1)^n$
Pick any $\delta>0$. Even though $(-1)^n$ oscillates, the magnitude is still $|a_n-0|=|n^{-1}(-1)^n|=n^{-1}$, so the same bound works: if $n\ge 1/\delta$, then $|a_n|\le \delta$, giving limit $0$.

The takeaway is that asymptotic analysis rests on a rigorous convergence definition, and you check it by bounding $|a_n-a|$ until it stays within any tolerance. Once you can do that, limits become a reliable approximation tool for large $n$.

**reasoning:**

Asymptotic analysis helps you approximate complicated behavior by looking at what happens when the sample size $n$ gets very large. The phrase “as $n\to\infty$” is a tool for approximation, not a claim about what happens at any finite $n$. This is why limits of sequences are the first building block you need.

> **Sequence convergence** the definition of convergence as $n\to\infty$ via the $delta$–$n_\delta$ condition

A sequence $a_n$ converges to $a$ as $n\to\infty$ exactly when, no matter how small you choose a tolerance $\delta>0$, you can find an index $n_\delta$ after which $a_n$ stays within $\delta$ of $a$. In symbols, this is the idea behind [[c1]]. The “big idea” is that convergence is about eventually staying close, not about being close at every step.

To prove convergence, you typically start with the inequality $|a_n-a|\le \delta$ and then solve for a condition on $n$ that guarantees it. That’s how you choose a valid $n_\delta$ rather than guessing. This approach is what makes the definition usable in real proofs.

### Example
For $a_n=n^{-1}$, you want $|a_n-0|=n^{-1}\le \delta$. If you choose $n\ge 1/\delta$, then the inequality holds, so the definition is satisfied with $a=0$ and $n_\delta=1/\delta$. This is the proof strategy captured in [[c2]].

### Example
For $a_n=n^{-1}(-1)^n$, the sign flips, but the magnitude still shrinks: $|a_n|=n^{-1}$. So to make $|a_n-0|\le \delta$, it’s enough to ensure $n^{-1}\le \delta$, which again happens whenever $n\ge 1/\delta$. The oscillation doesn’t matter because the absolute value still goes to $0$, as shown in [[c3]].

Putting it together: asymptotic analysis relies on limits, and limits of sequences are proved by the $delta$–$n_\delta$ “eventually close” condition. Once you learn to pick $n_\delta$ by forcing an inequality, you can handle both steady and oscillating sequences using the same core method.

### 7.3 CONVERGENCE IN PROBABILITY
**baseline:**

When you study data, you rarely see a single random variable—you see a whole sequence, like sample means as the sample size grows. So the key question becomes: in what sense does a sequence of random variables “approach” a limit? This is exactly what motivates the idea of [[c1]].

Deterministic convergence for numbers doesn’t directly apply to random variables, because randomness keeps changing the outcomes even as $n$ grows. That means we need a new definition that talks about probabilities of being far from the limit, not about exact equality.

To build intuition, it helps to compare different ways a random variable sequence can get “closer” to a target. For instance, probability mass might move toward the limit, or the variable might shrink toward the limit by scaling, or its spread might collapse as variance goes to zero.

One common way to formalize “getting close” is to look at what happens to the probability that the random variable differs from the limit by more than a small amount. This is the perspective behind [[c1]], which is widely used in econometrics because it matches how we reason about estimation and uncertainty.

### Example: Two-point distribution
Let $Z_n$ take values $0$ and $a_n$ with $\mathbb{P}[Z_n=0]=1-p_n$ and $\mathbb{P}[Z_n=a_n]=p_n$. It seems reasonable to say $Z_n$ converges to $0$ if either the “bad” probability $p_n\to 0$ or the “bad” value $a_n\to 0$.

### Example: Scaling a fixed random variable
Let $Z_n=b_n Z$, where $Z$ is a fixed random variable. Then it makes sense to expect $Z_n\to 0$ when the scaling factor satisfies $b_n\to 0$, because the whole random variable is being shrunk.

### Example: Variance shrinking
If $Z_n$ has variance $\sigma_n^2$ and $\sigma_n^2\to 0$, then the distribution is becoming more concentrated. That concentration suggests $Z_n$ is approaching $0$ in a “spread goes away” sense.

Putting these ideas together, convergence in probability captures the notion that the random variable becomes close to the limit with high probability. That’s why it’s such a central tool for describing how estimators behave as sample size increases.

**reasoning:**

A sequence of numbers can converge in a precise, deterministic way, but random variables keep changing because of randomness. That means we need a convergence idea that talks about probabilities of being “close” to the limit, not about exact equality. This is what lets us say a random sequence “approaches” a constant even though it never stops fluctuating.

Deterministic convergence won’t work for random variables, so we use a probabilistic definition of convergence that focuses on how likely $Z_n$ is to be far from the target. **Convergence in probability** is the most commonly used notion in econometrics because it matches how we reason about estimators becoming close to their true value with high probability. 

> **Convergence in probability** the sequence $Z_n$ converges in probability to $c$ if, for every tolerance level, the probability that $Z_n$ is more than that tolerance away from $c$ goes to 0 as $n$ grows.

Formally, $Z_n$ converges in probability to $c$ when the probability of a “noticeable deviation” shrinks to zero: [[c2]]. The key is that this must happen for every $ varepsilon>0$, so no matter how strict you are about closeness, $Z_n$ eventually stays close to $c$ with probability approaching 1.

### Example: Two-point distribution intuition
A two-point distribution helps build intuition for what “close with high probability” means. If $Z_n$ is 0 with probability $1-p_n$ and equals $a_n$ with probability $p_n$, then $Z_n$ should converge to 0 when either the “bad event” becomes rare ($p_n\to 0$) or the bad value itself becomes small ($a_n\to 0$). This matches the idea behind [[c3]].

### Example: Scaling by $b_n$
If $Z_n=b_n Z$ for some fixed random variable $Z$, then shrinking the multiplier $b_n$ forces $Z_n$ toward 0. As $b_n\to 0$, the random fluctuations get dampened, so $Z_n$ becomes close to 0 with high probability. That motivation is captured by [[c4]].

### Example: Variance going to 0
Variance provides another intuition: if the variance $ sigma_n^2$ of $Z_n$ goes to 0, then $Z_n$ concentrates around its mean (and in particular, around the constant you’re targeting). Even though $Z_n$ is still random, the spread collapses, making large deviations unlikely. This concentration idea is what [[c5]] is pointing you toward.

Putting it together, convergence in probability is a “closeness in probability” statement: deviations beyond any fixed tolerance become unlikely as $n$ grows. The examples show different mechanisms—rare bad outcomes, shrinking scale, or collapsing spread—that all lead to the same probabilistic behavior. That’s why this definition is such a practical tool for analyzing limits of random quantities in econometrics.

### 7.4 CHEBYSHEV'S INEQUALITY
**baseline:**

When you only know the mean and variance of a random variable, you still want a guarantee about how often it can stray far from its average. Chebyshev’s inequality gives exactly that kind of “no matter what the distribution is” control, which is why it becomes a central tool in proving the weak law of large numbers.

> **Chebyshev’s inequality** the probability that a random variable deviates from its mean by more than a fixed amount is at most the variance divided by the square of that amount.

In plain terms, if $X$ has mean $\mu$ and finite variance, then the tail probability $\mathbb{P}(|X-\mu|>\delta)$ can be bounded using only $\mathrm{Var}(X)$ and $\delta$, regardless of the shape of the distribution. This is the universal tail bound [[c2]] that depends on nothing except the second moment.

To start the derivation, it helps to center the variable by its mean: let $Z=X-\mu$. Then the event “$X$ is far from $\mu$” becomes the simpler event “$Z$ is large,” namely $|Z|\ge\delta$ [[c3]].

On the event $|Z|\ge\delta$, you can use the inequality $1\le Z^2/\delta^2$, which turns a probability statement into something involving $Z^2$. This leads to a worst-case tail rate that behaves like $\delta^{-2}$ among all distributions with finite variance [[c4]].

This “$\delta^{-2}$ worst-case” behavior matters because it is strong enough to control averages of many independent samples. Chebyshev’s inequality is the key step behind the weak law of large numbers [[c5]], which says sample averages concentrate around the true mean as the sample size grows.

### Example: Normal vs. Pareto tails
For a standard normal variable, $\mathbb{P}(|X|>\delta)$ decays very fast (roughly exponentially in $\delta$), while for a Pareto distribution it decays like a power law $\delta^{-\alpha}$. If $\alpha\le 2$, the variance is infinite, so Chebyshev’s inequality does not apply; among finite-variance cases, the slowest decay corresponds to the boundary behavior that leads to the $\delta^{-2}$ worst-case rate [[c4]].

Putting it all together: Chebyshev’s inequality turns limited information (mean and variance) into a guaranteed tail bound, and that guarantee is exactly what powers concentration results like the WLLN. The big takeaway is that finite variance rules out extremely heavy tails, forcing a universal $\delta^{-2}$-type control.

**reasoning:**

Suppose you only know the mean and variance of a random variable, but you still want to know how likely it is to deviate far from the mean. A universal tail bound like Chebyshev’s inequality gives you that control for *any* distribution with finite variance, without needing a specific formula for the density.

> **Chebyshev’s inequality** the definition…

Chebyshev’s inequality says that for any random variable with mean $\mu$ and finite variance $\mathrm{Var}(X)=\delta^2$ (with the usual notation), the probability of a large deviation is at most a constant times $1/\delta^2$, and it depends only on the variance. In other words, it bounds $\mathbb{P}(|X-\mu|>\delta)$ using only finite mean and variance, which is why it applies so broadly—this is the core idea behind [[c1]].

To derive the bound, the first move is to center the variable: let $Z=X-\mu$ so the event becomes $\{|Z|\ge\delta\}$. Then you express the tail probability as an integral over that tail region and compare it to an integral where the integrand is replaced by a larger quantity on the same region—this is the key step [[c2]].

On the tail region, the pointwise inequality $1\le Z^2/\delta^2$ lets you convert a probability statement into a statement about the second moment. When you carry this through, the resulting bound behaves like a worst-case power law: among all distributions with finite variance, the slowest possible decay of $\mathbb{P}(|X-\mu|>\delta)$ is on the order of $\delta^{-2}$, captured by [[c3]].

This “only $\delta^{-2}$” decay is slower than exponential tails, but it’s still strong enough to prove convergence in probability for averages. Chebyshev’s inequality is the key tool in the weak law of large numbers because it turns variance information about sums into a bound on the probability that the average stays far from its expected value—this connection is [[c4]].

### Example: Pareto-style power tails
If a distribution has power-law tails (like a Pareto with parameter $\alpha$), then $\mathbb{P}(|X-\mu|>\delta)$ decreases like a power of $\delta$ rather than exponentially. When $\alpha>2$ the variance is finite, and the slowest finite-variance behavior aligns with the $\delta^{-2}$ worst-case rate suggested by Chebyshev’s inequality.

The takeaway is that Chebyshev’s inequality is a universal “variance-to-tail” translator: it guarantees a $\delta^{-2}$-type control on deviations using only finite variance, and that guarantee is exactly what powers the weak law of large numbers.

### 7.5 WEAK LAW OF LARGE NUMBERS
**baseline:**

The weak law of large numbers matters because it tells you that averages of many independent observations “settle down” near the true mean. This lets you use the sample mean as a reliable stand-in for the population expectation, even before you know the exact distribution.

> **Weak Law of Large Numbers (WLLN)** the sample mean converges in probability to the population expectation as the sample size grows.

In plain terms, WLLN says that the sample mean becomes close to $\mathbb{E}[X]$ with high probability when $n$ is large, which is captured by [[c1]]. The key idea is convergence in probability: the probability of being far from the target goes to zero as $n$ increases, written as [[c2]].

To see why this happens, start with the sample mean’s behavior: it is unbiased for $\mu=\mathbb{E}[X]$, and its variance shrinks like $\sigma^2/n$. As $n\to\infty$, that variance goes to $0$, so the sample mean concentrates around $\mu$, which is why [[c4]] leads to convergence in probability.

This concentration is exactly what we mean by an estimator being “consistent.” If an estimator converges in probability to the true parameter as $n\to\infty$, then it is consistent, which is the property described by [[c3]].

Finally, WLLN can still hold even when the variance might be infinite, as long as the weaker condition $\mathbb{E}|X|<\infty$ is satisfied. That’s why the theorem uses [[c5]] rather than requiring finite variance.

### Example: Estimating a mean from data
If you observe i.i.d. values $X_1,\dots,X_n$ and compute the sample mean $\overline{X}_n$, then WLLN tells you that $\overline{X}_n$ will be arbitrarily close to $\mu=\mathbb{E}[X]$ with high probability for sufficiently large $n$.

Putting it all together: WLLN links the shrinking variability of the sample mean to convergence in probability, and that convergence is what makes the sample mean a consistent estimator of the population expectation. The big takeaway is that “more data” forces the average to behave like the true mean.

**reasoning:**

As you collect more observations, you want your estimates to “stabilize” around the truth. The weak law of large numbers gives exactly that guarantee for the sample mean: with enough data, it becomes very likely to be close to the population expectation.

### Example
Suppose you measure the same random quantity many times and compute the average each day; the weak law says that as the number of measurements grows, the daily average will be close to the true mean with high probability.

The key result is the weak law of large numbers for the sample mean: if $X_i$ are i.i.d. and $\mathbb{E}|X|<\infty$, then the sample mean converges in probability to $\mathbb{E}[X]$, which is the population mean. This is the [[c1]] Weak Law of Large Numbers (WLLN) for the sample mean.

> **Consistency** the definition via convergence in probability

In plain language, an estimator is consistent when its values get arbitrarily close to the true parameter as the sample size grows, in the sense of convergence in probability. That is the [[c2]] Consistency idea.

Because the sample mean satisfies $\bar X_n \xrightarrow[p]{} \mu$, the estimator $\hat\mu=\bar X_n$ must converge in probability to the true parameter $\mu=\mathbb{E}[X]$. So $\hat\mu$ is consistent for $\mu=\mathbb{E}[X]$, which is [[c3]] Consistency of $\hat\mu=\bar X_n$ for $\mu=\mathbb{E}[X]$.

Finally, the section emphasizes that while a variance-based argument is common, a more technical proof can establish the WLLN without assuming finite variance—only $\mathbb{E}|X|<\infty$ is needed. The takeaway is that “more data makes the sample mean reliable” is robust, not fragile.
