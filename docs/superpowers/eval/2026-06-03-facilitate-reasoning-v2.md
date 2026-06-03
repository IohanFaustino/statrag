# Facilitate map+teach — reasoning/CoT vs none (A/B) — v2 hardened prompts

_hansen ch07 §7.2–7.5 · 3 runs/variant · LLM-judge (1–5) · judge=gpt-5.4-nano-2026-03-17_

> **Verdict (v2 hardened prompts):** reasoning now wins **+0.17** overall (v1 was
> +0.01). non_expansion no longer regresses (2.42 tie). concept_id +0.34,
> faithfulness +0.17. Residual: **2** leaks across 4 sections (v1 had many) —
> one marker-adjacency (`The [[c2]] Chebyshev bound`) and one plan-speak
> blockquote (`> **Limit…** the definition…`). LaTeX clean. Clear net win;
> prompts could tighten the last 2 leaks before/at ship.

| variant | overall | clarity | faithfulness | keypoint_cov | non_expansion | concept_id |
|---|---|---|---|---|---|---|
| baseline | 3.53 | 4.0 | 3.5 | 3.92 | 2.42 | 3.83 |
| reasoning | 3.7 | 4.17 | 3.67 | 4.08 | 2.42 | 4.17 |

**Winner:** reasoning  (reasoning − baseline = +0.17)

## Sample bodies (run 1)

### 7.2 ASYMPTOTIC LIMITS
**baseline:**

Asymptotic analysis matters because it lets you understand what happens “in the long run” without computing everything exactly. Instead of working with finite sample sizes, you study what a sequence approaches as $n\to\infty$, using that limit as an approximation tool.

The key building block behind this idea is the concept of a limit of a sequence as $n\to\infty$, captured by [[c1]]. Once you know what it means for $a_n$ to converge to $a$, you can use that behavior to justify approximations in later arguments.

> **Limit (convergence) of a sequence** the definition…  

In plain terms, [[c1]] means: no matter how tight a tolerance you choose around $a$, the sequence eventually stays inside that tolerance forever. The “eventually” part is what makes it useful for approximation.

With convergence in hand, [[c2]] is the method of using that limiting behavior to approximate complicated quantities. You treat the limit as a stand-in for large-$n$ behavior, even though you never literally reach $n=\infty$ in real problems.

A practical way to check convergence is the criterion [[c3]]. It says that for every $\delta>0$, you can find a point $n_\delta$ after which all terms satisfy $|a_n-a|\le \delta$.

### Example: $a_n=n^{-1}$
Let $\delta>0$ and choose $n\ge 1/\delta$; then $|a_n-0|=n^{-1}\le \delta$. So the convergence definition is satisfied with limit $a=0$, meaning $a_n\to 0$.

### Example: $a_n=n^{-1}(-1)^n$
Even though $(-1)^n$ flips the sign, the distance to $0$ is $|a_n-0|=|n^{-1}(-1)^n|=n^{-1}$. For $n\ge 1/\delta$, we again get $n^{-1}\le \delta$, so $a_n\to 0$.

Putting it together: asymptotic analysis relies on the convergence definition to turn “large $n$ behavior” into a reliable approximation. Once you can show $a_n$ gets arbitrarily close to $a$ and stays there, you can confidently use the limit as your asymptotic guide.

**reasoning:**

Asymptotic analysis is useful because it turns complicated behavior into something we can approximate by looking at what happens when the sample size $n$ gets very large. The notation $n\to\infty$ is not a literal story about infinite data; it’s a tool for understanding how errors shrink for large $n$. This is exactly why limits of sequences matter.

> **Definition of convergence of a sequence as $n\to\infty$ (the $\delta$–$n_\delta$ criterion)** the sequence $a_n$ converges to $a$ as $n\to\infty$ if for every $\delta>0$ there exists an $n_\delta$ such that for all $n\ge n_\delta$, $|a_n-a|\le\delta$.

The key idea in the definition is the “for every tolerance” part: no matter how small you want the error to be (that’s $\delta$), you can go far enough out in the sequence (that’s $n_\delta$) so the inequality $|a_n-a|\le\delta$ holds forever after. So proving convergence is really about choosing a suitable $n_\delta$ that makes the distance from $a$ stay within your chosen tolerance.

To prove convergence, you typically start by fixing an arbitrary $\delta>0$, then find a condition on $n$ that guarantees $|a_n-a|\le\delta$. Once you have that condition, you can translate it into a specific choice of $n_\delta$ and conclude the definition is satisfied.

### Example: $a_n=n^{-1}$
Pick any $\delta>0$ and require $n\ge 1/\delta$; then $|a_n-0|=n^{-1}\le\delta$. This works for all $n\ge n_\delta$ with $n_\delta=1/\delta$, so the sequence converges to $0$.

### Example: $a_n=n^{-1}(-1)^n$
Here the sign flips, but the magnitude does not: $|(-1)^n|=1$, so $|a_n-0|=|n^{-1}(-1)^n|=n^{-1}$. Using the same step as before, if $n\ge 1/\delta$ then $n^{-1}\le\delta$, so the sequence also converges to $0$.

The takeaway is that asymptotic reasoning rests on a precise way to control error: convergence means you can make $|a_n-a|$ smaller than any chosen $\delta$ by going to sufficiently large $n$. Once you get comfortable picking $n_\delta$, many asymptotic results become straightforward to verify.

### 7.3 CONVERGENCE IN PROBABILITY
**baseline:**

When we study data, we often look at sequences like sample means, but their distributions keep changing as $n$ grows. That means we need a way to say “the random variable is getting close to a limit” even though it never becomes a fixed number. This is exactly what [[c1]] gives us.

Deterministic convergence for numbers doesn’t directly apply to random variables, because a random variable can keep fluctuating while its probability mass shifts. So we introduce a convergence idea that measures how often the random variable is far from the target. That leads to the standard definition captured by [[c2]].

To build intuition, imagine a two-point random variable that is usually at 0 but sometimes jumps to a value $a_n$. If the jump probability $p_n$ goes to 0, then the variable is almost always near 0; if the jump size $a_n$ goes to 0, then even the rare jump becomes negligible. This is the kind of “approaching” behavior described by [[c3]].

Another way a sequence can approach a limit is by scaling: if $Z_n=b_n Z$ and the scale factor $b_n$ shrinks to 0, then the whole random variable gets squeezed toward 0. Even though $Z$ may vary, multiplying by something going to 0 makes large deviations less likely. This scaling intuition is summarized by [[c4]].

A third intuition comes from variance: if the variance $\sigma_n^2$ of $Z_n$ goes to 0, then the distribution concentrates more and more tightly around its mean (and in particular around 0 in the examples here). Small variance means it becomes unlikely that $Z_n$ differs from the limit by more than a small amount. This “variance shrinking” route to convergence is captured by [[c5]].

Putting these together, convergence in probability is the idea that “being far from $c$” becomes increasingly unlikely as $n$ grows. In econometrics, this is the go-to notion because it matches how we reason about random fluctuations becoming negligible in large samples.

### Example: Two-point distribution
Let $Z_n$ take values $0$ and $a_n$ with probabilities $1-p_n$ and $p_n$. Then $Z_n$ converges in probability to $0$ if either $p_n\to 0$ (jumps become rare) or $a_n\to 0$ (jumps become small), matching the intuition in [[c3]].

### Example: Scaling to zero
If $Z_n=b_n Z$ for some random variable $Z$ and $b_n\to 0$, then $Z_n$ converges in probability to $0$ because the factor $b_n$ forces the whole random variable toward 0. This is the mechanism behind [[c4]].

### Example: Variance shrinking
If $\mathrm{Var}(Z_n)=\sigma_n^2$ and $\sigma_n^2\to 0$, then $Z_n$ concentrates near $0$, making it unlikely that $Z_n$ differs from $0$ by more than a small tolerance. That concentration idea is what [[c5]] is pointing to.

**reasoning:**

A sequence of numbers can converge in a straightforward way, but random variables keep changing in unpredictable ways. That means we need a probabilistic notion of convergence—one that tells us how likely it is that $Z_n$ is close to the limit. This lets us talk about “limits” for objects like sample means.

Since $Z_n$ is random, we cannot use the deterministic idea of “eventually equal” or “eventually within a fixed distance” for every outcome. Instead, we measure closeness using probabilities, so the definition can reflect that some outcomes may still wander away.

To build intuition, it helps to look at what it could mean for a random variable sequence $Z_n$ to “converge to 0,” and that’s where the three motivating examples come in: [[c2]].

### Example: Probability mass shrinking
Suppose $Z_n$ takes values $0$ and $a_n$ with $
\mathbb{P}[Z_n=0]=1-p_n$ and $\mathbb{P}[Z_n=a_n]=p_n$. Then it makes sense to say $Z_n$ converges to $0$ if the “bad” event becomes rare, meaning $p_n\to 0$ (or if the nonzero value itself shrinks, meaning $a_n\to 0$).

### Example: Scaling to 0
If $Z_n=b_n Z$ for some fixed random variable $Z$, then $Z_n$ is just a scaled version of $Z$. In this case, it’s natural to expect $Z_n\to 0$ when the scaling factor shrinks, i.e., when $b_n\to 0$.

### Example: Variance shrinking
If $Z_n$ has variance $\sigma_n^2$, then a small variance indicates that $Z_n$ is typically clustered near its mean. So it’s reasonable to expect $Z_n\to 0$ when the spread collapses, i.e., when $\sigma_n^2\to 0$.

Multiple convergence concepts exist for random variables, but the one most commonly used in econometrics is convergence in probability: [[c1]].

> **Convergence in probability** A sequence of random variables $Z_n\in\mathbb{R}$ converges in probability to $c$ as $n\to\infty$ if for every $\varepsilon>0$, $\mathbb{P}(|Z_n-c|>\varepsilon)\to 0$.

This definition formalizes “being close to the limit” using a tolerance $\varepsilon$: as $n$ grows, the probability that $Z_n$ differs from $c$ by more than $\varepsilon$ must go to zero. In other words, $Z_n$ becomes unlikely to be far from $c$, even if it may still occasionally deviate.

Putting it together, the examples show three different ways randomness can “collapse” toward a limit: less probability on far values, smaller scaling, or shrinking spread. Convergence in probability captures all of these through one consistent rule about how unlikely large deviations become.

### 7.4 CHEBYSHEV'S INEQUALITY
**baseline:**

When you only know that a random variable has a finite mean and finite variance, you still want a guarantee about how often it can stray far from its mean. Chebyshev’s inequality gives a universal way to bound that “far away” probability, without needing the exact distribution. This matters because it works uniformly across all distributions that meet the variance requirement.

> **Chebyshev’s inequality** the probability that a random variable deviates from its mean by more than $\delta$ is at most the variance divided by $\delta^2$.

In plain terms, if $X$ has mean $\mu$ and finite variance, then the chance that $X$ differs from $\mu$ by more than $\delta$ is controlled by how big the variance is, scaled by $\delta^2$. This is captured by [[c1]].

That control only makes sense when the variance is finite, which rules out heavy-tailed distributions that don’t have enough decay. For example, a Pareto distribution needs its tail exponent to satisfy $\alpha>2$ so that the second moment exists, which is exactly the “finite variance” requirement [[c2]].

Among all distributions with finite variance, the slowest possible tail decay (the worst case) behaves like a power law. In particular, the bound scales like $\delta^{-2}$, meaning the probability can’t be forced to drop faster than on the order of $\delta^{-2}$ in the worst case [[c3]].

This worst-case tail control is the engine behind the weak law of large numbers: averages concentrate around their expected value, but the proof uses only second-moment information. Chebyshev’s inequality turns “finite variance” into a quantitative statement that deviations become unlikely as the sample size grows, which is why it is central to [[c4]].

To derive the inequality, start by centering the variable: let $Z=X-\mu$. Then the event $\{|X-\mu|\ge \delta\}$ becomes $\{|Z|\ge \delta\}$, and you can express its probability as an integral over the region where $|x|\ge \delta$, which sets up the calculation in [[c5]].

On the region where $|x|\ge \delta$, you can use the simple fact that $1\le x^2/\delta^2$. That lets you upper-bound the indicator of the event by a scaled version of $x^2$, so the probability is at most a constant times the second moment (the variance), yielding the universal $\delta^{-2}$ form.

Putting it all together, Chebyshev’s inequality is a worst-case, variance-based bound: it guarantees concentration using only finite mean and finite variance. The key takeaway is that the $\delta^{-2}$ scaling is not just a convenient estimate—it reflects the slowest tail behavior compatible with finite variance, and it powers results like the WLLN.

**reasoning:**

When you only know that a random variable has a mean and a finite variance, you still want to control how often it can wander far from its mean. That’s what makes a distribution-free tail bound so useful: it gives a guarantee that works for every distribution, not just the ones you can compute exactly.

Chebyshev’s inequality, the [[c1]] result, tells you how to bound the probability of a large deviation using only the variance. It applies to any random variable with finite mean and finite variance, no matter what the distribution looks like. The big idea is that variance alone is enough to control the tail probability.

### Example
If $X$ is standard normal, then $
\mathbb{P}(|X|>\delta)$ decays very fast with $
\delta$; if $X$ is logistic, it also decays, but more slowly than the normal. For a Pareto-type tail, $
\mathbb{P}(|X|>\delta)$ behaves like a power law $
\delta^{-\alpha}$, so it can decay much more slowly than exponential tails. This contrast is exactly why a worst-case bound must be based on variance rather than on “nice” tail shapes.

The [[c2]] Chebyshev bound is the explicit inequality: $
\mathbb{P}(|X-\mu|>\delta)\le \mathrm{Var}(X)/\delta^2$. To see where it comes from, define $Z=X-\mu$ so the event becomes $|Z|>\delta$, and then rewrite the probability as an integral over the tail region $\{|x|\ge\delta\}$. On that region, you use the pointwise fact that $1\le x^2/\delta^2$ to upper-bound the integrand by something involving $x^2$.

This derivation leads to the [[c3]] worst-case tail rate: among all distributions with finite variance, the slowest possible decay matches the $\delta^{-2}$ scaling. The finite-variance requirement rules out Pareto tails with $\alpha\le 2$, because those would have infinite variance and therefore can’t be worst-case under Chebyshev’s assumptions. The big idea is that, within the finite-variance world, no distribution can make the tail probability decay slower than the $\delta^{-2}$ rate.

Putting it together, Chebyshev’s inequality gives a universal “safety bound” on deviations from the mean using only variance. The derivation shows why the $\delta^{-2}$ form is inevitable, and the worst-case discussion explains why you can’t hope for a faster guaranteed rate without extra assumptions about the distribution’s tail.

### 7.5 WEAK LAW OF LARGE NUMBERS
**baseline:**

When you compute the sample mean from data, you want it to “settle down” near the true average as you collect more observations. The weak law of large numbers tells you exactly what kind of settling happens—so you can trust averages more and more as $n$ grows.

> **Weak Law of Large Numbers (WLLN)** the sample mean converges in probability to the population mean as the sample size grows.

This means that, under the right conditions, the sample mean becomes close to $\mathbb{E}[X]$ with probability approaching 1, which is captured by [[c2]]. In other words, the randomness doesn’t disappear, but the chance of being far from the truth goes to zero.

A key reason this works is that the sample mean has an error that shrinks as $n$ increases: it is unbiased for $\mu=\mathbb{E}[X]$, and its variance is $\sigma^2/n$, which goes to 0. That shrinking variability is what drives the convergence in probability described by the WLLN, which is why [[c1]] is so useful.

The WLLN also connects to a broader idea: what it means for an estimator to be reliable as data size increases. An estimator is called consistent if it converges in probability to the true parameter as $n\to\infty$, which is the definition captured by [[c3]].

Finally, the sample mean itself is a prime example of a consistent estimator. Under the WLLN assumptions, $\widehat{\mu}=\overline{X}_n$ converges in probability to $\mu=\mathbb{E}[X]$, so [[c4]] is consistent.

### Example
If $X_1,\dots,X_n$ are i.i.d. with $\mathbb{E}|X|<\infty$, then the sample mean $\overline{X}_n$ will be close to $\mu=\mathbb{E}[X]$ with high probability for large $n$, even if $\mathrm{Var}(X)$ is infinite.

Putting it all together: the sample mean’s shrinking uncertainty leads to convergence in probability, which is exactly what the weak law guarantees. Consistency is the estimator-level takeaway, and the sample mean is consistent under the WLLN conditions.

**reasoning:**

When you estimate an unknown quantity from data, you want the estimate to “settle down” as you collect more observations. The weak law of large numbers tells you that the sample mean becomes close to the population expectation with high probability, even when variance might be infinite. That’s what makes it a powerful justification for using averages in real problems.

The [[c1]] result says that the sample mean converges in probability to the population mean as $n\to\infty$ under i.i.d. sampling and the condition $\mathbb{E}|X|<\infty$. Importantly, this generalizes earlier arguments that relied on finite variance, because it does not require $\mathrm{Var}(X)<\infty$. So you still get reliable averaging behavior under weaker assumptions.

> **Consistency** the property that an estimator converges in probability to the true parameter as the sample size grows.

In plain terms, [[c2]] means that for large enough $n$, the estimator can be made arbitrarily close to the target parameter with high probability. This is exactly the kind of “long-run correctness” you want from an estimator.

The [[c3]] statement is the concrete form of the WLLN: the sample mean $\overline{X}_n=\frac{1}{n}\sum_{i=1}^n X_i$ converges in probability to $\mathbb{E}[X]$ when the $X_i$ are i.i.d. and $\mathbb{E}|X|<\infty$. This is the bridge from a probabilistic limit theorem to an estimation guarantee.

### Example: Estimating the mean
If you use $\widehat{\mu}=\overline{X}_n$ to estimate $\mu=\mathbb{E}[X]$, then by the WLLN you can choose $n$ large enough so that $\overline{X}_n$ is within any pre-specified tolerance of $\mu$ with probability as close to $1$ as you like.

Putting it together: WLLN tells you the sample mean converges in probability to the expectation, and that convergence is what we call consistency for the corresponding estimator. The key takeaway is that you can justify using averages for estimation under the weaker requirement $\mathbb{E}|X|<\infty$, not necessarily finite variance.
