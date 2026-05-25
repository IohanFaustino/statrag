// Canned conversation data for statrag prototype

window.STATRAG_BOOKS = [
  {
    id: "ISLP",
    title: "An Introduction to Statistical Learning",
    subtitle: "with Applications in Python",
    short: "ISLP",
    authors: "James, Witten, Hastie, Tibshirani, Taylor",
    authorsShort: "James et al.",
    edition: "2nd ed. · Springer · 2023",
    chunks: 1247,
    figures: 184,
    chapters: 13,
    color: "#7EC8A4",
    cover: "islp",
    description: "A modern, accessible treatment of statistical learning with Python implementations. Used widely as an introductory text in applied ML and applied statistics courses.",
    collection: "islp_chunks",
    selected: true,
  },
  {
    id: "HANSEN",
    title: "Econometrics",
    subtitle: "Theory and applications for the working researcher",
    short: "Hansen",
    authors: "Bruce E. Hansen",
    authorsShort: "Hansen",
    edition: "Princeton University Press · 2022",
    chunks: 982,
    figures: 67,
    chapters: 26,
    color: "#E8A87C",
    cover: "hansen",
    description: "A graduate-level econometrics text emphasising asymptotic theory, identification, and the analytical underpinnings of regression-based methods.",
    collection: "hansen_chunks",
    selected: true,
  },
  {
    id: "ESL",
    title: "The Elements of Statistical Learning",
    subtitle: "Data Mining, Inference, and Prediction",
    short: "ESL",
    authors: "Hastie, Tibshirani, Friedman",
    authorsShort: "Hastie et al.",
    edition: "2nd ed. · Springer · 2009",
    chunks: 1683,
    figures: 218,
    chapters: 18,
    color: "#9B8FCC",
    cover: "esl",
    description: "The graduate companion to ISLP. Denser treatment of theory, more depth on advanced methods. Not currently indexed in this corpus.",
    collection: "esl_chunks",
    selected: false,
    indexed: false,
  },
  {
    id: "WOOLDRIDGE",
    title: "Econometric Analysis",
    subtitle: "of Cross Section and Panel Data",
    short: "Wooldridge",
    authors: "Jeffrey M. Wooldridge",
    authorsShort: "Wooldridge",
    edition: "2nd ed. · MIT Press · 2010",
    chunks: 1421,
    figures: 42,
    chapters: 21,
    color: "#4F9CF9",
    cover: "wooldridge",
    description: "Comprehensive reference for cross-sectional and panel methods. Complements Hansen with deeper applied treatment of fixed effects and IV.",
    collection: "wooldridge_chunks",
    selected: false,
    indexed: false,
  },
];

window.STATRAG_CONVERSATIONS = {
  today: [
    { id: "c1", title: "Ridge vs OLS in Hansen", mode: "tutor", active: true },
    { id: "c2", title: "Cross-validation pitfalls", mode: "tutor" },
  ],
  yesterday: [
    { id: "c3", title: "Bootstrap resampling — when to use", mode: "tutor" },
    { id: "c4", title: "Quiz: Linear regression assumptions", mode: "quiz" },
  ],
  thisWeek: [
    { id: "c5", title: "Path: Trees → Random Forests → Boosting", mode: "path" },
    { id: "c6", title: "Annotate: A reviewer comment", mode: "annotate" },
    { id: "c7", title: "GAM vs spline regression", mode: "tutor" },
  ],
  earlier: [
    { id: "c8", title: "Compare LASSO derivations", mode: "compare" },
    { id: "c9", title: "Find Hansen's M-estimator section", mode: "navigate" },
    { id: "c10", title: "Prereqs for asymptotic normality", mode: "prereqs" },
  ],
};

window.STATRAG_ROADMAPS = [
  { id: "r1", title: "Bias-Variance Tradeoff", scenes: 11, date: "May 12" },
  { id: "r2", title: "From OLS to Ridge to LASSO", scenes: 8, date: "May 09" },
  { id: "r3", title: "Cross-Validation in Practice", scenes: 6, date: "Apr 28" },
];

window.STATRAG_MODES = [
  { id: "tutor",    label: "Tutor",    glyph: "T", icon: "book" },
  { id: "compare",  label: "Compare",  glyph: "C", icon: "compare" },
  { id: "figures",  label: "Figures",  glyph: "F", icon: "image" },
  { id: "quiz",     label: "Quiz",     glyph: "Q", icon: "quiz" },
  { id: "navigate", label: "Navigate", glyph: "N", icon: "search" },
  { id: "prereqs",  label: "Prereqs",  glyph: "P", icon: "tree" },
  { id: "annotate", label: "Annotate", glyph: "A", icon: "pen" },
  { id: "research", label: "Research", glyph: "R", icon: "flask" },
  { id: "math",     label: "Math",     glyph: "∑", icon: "sigma" },
  { id: "path",     label: "Path",     glyph: "✦", icon: "cal" },
  { id: "roadmap",  label: "Roadmap",  glyph: "▶", icon: "film" },
];

// The canned conversation, mid-thread
window.STATRAG_THREAD = [
  {
    role: "user",
    time: "14:31",
    text: "How does Ridge regression differ from OLS in Hansen's treatment? I want to understand the shrinkage interpretation specifically.",
  },
  {
    role: "assistant",
    mode: "tutor",
    books: ["ISLP", "HANSEN"],
    sourceCount: 3,
    latencyMs: 820,
    blocks: [
      {
        type: "p",
        text: "Ridge regression extends ordinary least squares by adding an $L_2$ penalty term to the loss function. Where OLS minimizes only the residual sum of squares, Ridge introduces a tuning parameter $\\lambda \\geq 0$ that shrinks coefficients toward zero:",
      },
      {
        type: "math",
        tex: "\\hat{\\beta}_{\\text{ridge}} = \\arg\\min_{\\beta} \\;\\bigl\\lVert y - X\\beta \\bigr\\rVert_2^2 \\;+\\; \\lambda \\bigl\\lVert \\beta \\bigr\\rVert_2^2",
      },
      {
        type: "p",
        text: "**Hansen (ch07, §7.4)** frames this explicitly as a *shrinkage estimator*, deriving the closed form $\\hat{\\beta}_{\\text{ridge}} = (X^\\top X + \\lambda I_p)^{-1} X^\\top y$ and emphasizing that the $\\lambda I_p$ term guarantees invertibility even when $X^\\top X$ is singular — the original motivation in Hoerl & Kennard (1970). The bias-variance tradeoff is foregrounded: as $\\lambda \\to 0$ Ridge collapses to OLS (unbiased, high-variance); as $\\lambda \\to \\infty$ all coefficients vanish (zero variance, maximal bias).",
      },
      {
        type: "p",
        text: "**ISLP (ch06, §6.2)** takes a different angle — Ridge is introduced as one of several *model selection / regularization* techniques, alongside LASSO and best-subset selection. The pedagogical emphasis is on predictive accuracy on held-out data rather than estimator theory.",
      },
      {
        type: "p",
        text: "Both texts converge on the same practical point: Ridge is most useful when predictors are correlated and OLS variance explodes. Hansen treats this analytically through condition numbers; ISLP demonstrates it empirically on the Credit dataset.",
      },
      {
        type: "sources",
        chips: [
          { book: "HANSEN", section: "ch07 §7.4" },
          { book: "ISLP",   section: "ch06 §6.2" },
          { book: "ISLP",   section: "ch06 §6.2.1" },
        ],
      },
    ],
  },
  {
    role: "user",
    time: "14:34",
    text: "Show me the bias-variance picture as λ varies.",
  },
  {
    role: "assistant",
    mode: "tutor",
    books: ["ISLP"],
    sourceCount: 2,
    latencyMs: 640,
    blocks: [
      {
        type: "p",
        text: "ISLP fig. 6.4 plots squared bias, variance, and test MSE against $\\lambda$ (on a log scale). The decomposition is:",
      },
      {
        type: "math",
        tex: "\\mathrm{MSE}(\\hat{f}(x_0)) = \\underbrace{\\bigl(\\mathbb{E}\\hat{f}(x_0) - f(x_0)\\bigr)^2}_{\\text{Bias}^2} \\;+\\; \\underbrace{\\mathrm{Var}(\\hat{f}(x_0))}_{\\text{Variance}} \\;+\\; \\sigma^2",
      },
      {
        type: "figure",
        ref: "fig_6_4",
        book: "ISLP",
        chapter: "ch06",
        caption: "Bias-variance tradeoff as λ varies. Test MSE (purple) is minimized at moderate shrinkage.",
        chart: "biasvar",
      },
      {
        type: "p",
        text: "As $\\lambda$ increases from zero: variance falls monotonically (less sensitivity to training noise) while squared bias rises monotonically (estimator pulled away from the truth). Test MSE is U-shaped; the minimum occurs at the $\\lambda$ where the marginal variance reduction equals the marginal bias increase.",
      },
      {
        type: "sources",
        chips: [
          { book: "ISLP",   section: "ch06 §6.2.2" },
          { book: "HANSEN", section: "ch07 §7.5" },
        ],
      },
    ],
  },
];

// Retrieved sources for the most recent assistant turn
window.STATRAG_SOURCES = [
  {
    rank: 1,
    book: "ISLP",
    chapter: "ch06",
    section: "§6.2.2",
    title: "The Bias-Variance Tradeoff",
    excerpt: "...the variance decreases monotonically while the squared bias increases monotonically as λ grows; the test MSE is therefore U-shaped...",
    score: 0.94,
    page: 247,
    chunkId: "islp_ch06_p247_b3",
    embedding: "BAAI/bge-large-en-v1.5",
    chunk: "Why does ridge regression improve over least squares? Its advantage is rooted in the bias-variance tradeoff. As the tuning parameter λ increases, the flexibility of the ridge regression fit decreases, leading to decreased variance but increased bias. This is illustrated in Figure 6.5, using a simulated data set containing p = 45 predictors and n = 50 observations. The green curve in the left-hand panel of Figure 6.5 displays the variance of the ridge regression predictions as a function of λ. At the least squares coefficient estimates, which correspond to λ = 0, the variance is high but there is no bias. But as λ increases, the shrinkage of the ridge coefficient estimates leads to a substantial reduction in the variance of the predictions, at the expense of a slight increase in bias. Recall that the test mean squared error (MSE), plotted in purple, is a function of the variance plus the squared bias. For values of λ up to about 10, the variance decreases rapidly, with very little increase in bias, plummeting the MSE. As λ increases beyond this point, the variance decreases slowly while the bias rises rapidly, causing a sharp increase in the MSE. The bias and variance curves both flatten out for very large λ.",
    highlights: [
      "the variance of the ridge regression predictions as a function of λ",
      "the variance decreases rapidly, with very little increase in bias",
      "test mean squared error (MSE), plotted in purple, is a function of the variance plus the squared bias",
    ],
  },
  {
    rank: 2,
    book: "HANSEN",
    chapter: "ch07",
    section: "§7.5",
    title: "MSE Decomposition for Ridge",
    excerpt: "...for the ridge estimator the mean-squared error decomposes as the squared bias term plus the variance term, both functions of the shrinkage parameter...",
    score: 0.89,
    page: 198,
    chunkId: "hansen_ch07_p198_b1",
    embedding: "BAAI/bge-large-en-v1.5",
    chunk: "The mean-squared error of the ridge estimator admits a closed-form decomposition that is instructive for understanding its behaviour. Writing β̂(λ) = (X⊤X + λI_p)⁻¹X⊤y, and denoting W(λ) = (X⊤X + λI_p)⁻¹X⊤X, we have E[β̂(λ)] = W(λ)β. The bias is therefore (W(λ) − I_p)β, and the variance is σ² W(λ)(X⊤X)⁻¹W(λ). Both terms depend on λ in opposing directions. As λ → 0, W(λ) → I_p, so the bias vanishes and the variance approaches the OLS variance σ²(X⊤X)⁻¹. As λ → ∞, W(λ) → 0, the bias approaches −β (estimator collapses to zero), and the variance vanishes. Between these extremes, MSE = tr(Bias·Bias⊤) + tr(Var) describes a U-shaped curve in λ. Theobald (1974) showed that for sufficiently small but positive λ, the ridge MSE is strictly lower than the OLS MSE under any choice of β — a striking result that motivates the use of shrinkage even when one has no prior preference for smaller coefficients.",
    highlights: [
      "MSE = tr(Bias·Bias⊤) + tr(Var) describes a U-shaped curve in λ",
      "both terms depend on λ in opposing directions",
    ],
  },
  {
    rank: 3,
    book: "ISLP",
    chapter: "ch06",
    section: "§6.2.1",
    title: "Ridge Regression",
    excerpt: "...the penalty term λΣβⱼ² shrinks the coefficients toward zero, with the amount of shrinkage controlled by the tuning parameter...",
    score: 0.81,
    page: 240,
    chunkId: "islp_ch06_p240_b2",
    embedding: "BAAI/bge-large-en-v1.5",
    chunk: "Ridge regression is very similar to least squares, except that the coefficients are estimated by minimizing a slightly different quantity. In particular, the ridge regression coefficient estimates β̂^R are the values that minimize ∑(yᵢ − β₀ − ∑βⱼxᵢⱼ)² + λ∑βⱼ², where λ ≥ 0 is a tuning parameter, to be determined separately. As with least squares, ridge regression seeks coefficient estimates that fit the data well, by making the RSS small. However, the second term, λ∑βⱼ², called a shrinkage penalty, is small when β₁,...,β_p are close to zero, and so it has the effect of shrinking the estimates of βⱼ towards zero. The tuning parameter λ serves to control the relative impact of these two terms on the regression coefficient estimates. When λ = 0, the penalty term has no effect, and ridge regression will produce the least squares estimates. However, as λ → ∞, the impact of the shrinkage penalty grows, and the ridge regression coefficient estimates will approach zero.",
    highlights: [
      "the second term, λ∑βⱼ², called a shrinkage penalty",
      "the effect of shrinking the estimates of βⱼ towards zero",
      "When λ = 0, the penalty term has no effect, and ridge regression will produce the least squares estimates",
    ],
  },
  {
    rank: 4,
    book: "HANSEN",
    chapter: "ch07",
    section: "§7.4",
    title: "Shrinkage Estimators",
    excerpt: "...Hoerl & Kennard (1970) introduced ridge regression to address the numerical instability of OLS when X⊤X is near-singular...",
    score: 0.74,
    page: 192,
    chunkId: "hansen_ch07_p192_b4",
    embedding: "BAAI/bge-large-en-v1.5",
    chunk: "Hoerl and Kennard (1970) introduced the ridge regression estimator as a remedy for the numerical instability of ordinary least squares in the presence of near-collinearity among regressors. When X⊤X is ill-conditioned, small perturbations in the data produce wild changes in β̂_OLS = (X⊤X)⁻¹X⊤y. The ridge solution β̂(λ) = (X⊤X + λI_p)⁻¹X⊤y replaces the inversion of X⊤X with that of X⊤X + λI_p, which is guaranteed to be positive definite whenever λ > 0. This stabilises the inverse and yields a unique, well-behaved estimator. The original motivation was thus computational rather than statistical; the connection to bias-variance tradeoffs and Bayesian priors came later. Hoerl and Kennard's central observation was that even when β̂_OLS exists, the ridge estimator can attain lower mean-squared error by tolerating a small bias in exchange for a substantial reduction in variance.",
    highlights: [
      "Hoerl and Kennard (1970) introduced the ridge regression estimator as a remedy for the numerical instability of ordinary least squares",
      "the ridge estimator can attain lower mean-squared error by tolerating a small bias in exchange for a substantial reduction in variance",
    ],
  },
];

window.STATRAG_FIGURES = [
  {
    ref: "fig_6_4",
    book: "ISLP",
    chapter: "ch06",
    caption: "Bias-variance tradeoff as λ varies",
    chart: "biasvar",
  },
  {
    ref: "fig_6_5",
    book: "ISLP",
    chapter: "ch06",
    caption: "Standardized ridge coefficients vs λ",
    chart: "paths",
  },
];

window.STATRAG_METADATA = {
  rewrittenQuery: "ridge regression bias variance tradeoff lambda visualization",
  embedding: "BAAI/bge-large-en-v1.5",
  retrievalMs: 142,
  collections: ["islp_chunks", "hansen_chunks", "islp_figures"],
  filter: "book ∈ {ISLP, HANSEN}",
  topK: 5,
  scoreThreshold: 0.60,
  mode: "hybrid (sparse 0.3 + dense 0.7)",
};

// ─── Model providers ────────────────────────────────────────────────────────
window.STATRAG_PROVIDERS = [
  {
    id: "openai",
    name: "OpenAI",
    color: "#10A37F",
    short: "OAI",
    models: [
      { id: "gpt-4o",       name: "GPT-4o",       tagline: "Fast multimodal",     cost: "$$$",  speed: "fast", ctx: "128k" },
      { id: "gpt-4o-mini",  name: "GPT-4o mini",  tagline: "Cheapest tier",       cost: "$",    speed: "fast", ctx: "128k" },
      { id: "gpt-4.1",      name: "GPT-4.1",      tagline: "Smartest general",    cost: "$$$$", speed: "med",  ctx: "1M"   },
      { id: "o3-mini",      name: "o3-mini",      tagline: "Reasoning, hidden CoT", cost: "$$",   speed: "slow", ctx: "200k" },
    ],
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    color: "#4D6BFE",
    short: "DS",
    models: [
      { id: "deepseek-v3",  name: "DeepSeek V3",  tagline: "Chat & code, open",   cost: "$",    speed: "fast", ctx: "64k"  },
      { id: "deepseek-r1",  name: "DeepSeek R1",  tagline: "Open reasoning",      cost: "$",    speed: "slow", ctx: "64k"  },
    ],
  },
];

window.STATRAG_DEFAULT_MODEL = "gpt-4o";
