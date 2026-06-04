# Formula reference (load on demand)

State the *defining* formula of every component you name. Examples of the expected pattern:

- **Bias–variance** (a decomposition concept):
  - Bias: $\operatorname{Bias}(\hat f) = \mathbb{E}[\hat f] - f$
  - Variance: $\operatorname{Var}(\hat f) = \mathbb{E}\big[(\hat f - \mathbb{E}[\hat f])^2\big]$
  - Decomposition (central quantity): $$\operatorname{MSE}(\hat f) = \operatorname{Bias}(\hat f)^2 + \operatorname{Var}(\hat f) + \sigma^2$$
- **AR(p) / MA(q)** (a representation concept):
  - $Y_t = \phi_1 Y_{t-1} + \dots + \phi_p Y_{t-p} + \varepsilon_t$
  - $Y_t = \varepsilon_t + \theta_1 \varepsilon_{t-1} + \dots + \theta_q \varepsilon_{t-q}$

Rule: when a concept decomposes into named parts, each part's `###` subsection opens with a bullet stating that part's formula inline; a final `###` for the central quantity states the `$$decomposition$$`.
