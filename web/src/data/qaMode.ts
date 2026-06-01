// Description of the Q&A mode itself (the modal opens from the Q&A card).
export const QA_MODE = {
  title: "Q&A mode",
  blurb: "Punctual, source-grounded answers",
  description:
    "Q&A mode answers a single, focused question with a terse, directly-grounded reply built only from the indexed books. It narrows your question to the actual gap, retrieves a small high-precision set of sources, writes a scoped answer that skips what you already know, and audits each claim against the sources.",
  features: [
    { label: "Gap-scoped", detail: "Parses your question into {target gap, assumed-known, answer form} so it answers only what's missing." },
    { label: "High-precision retrieval", detail: "Hybrid dense + sparse search reranked to a small top-k for focused, low-noise context." },
    { label: "Per-claim citations", detail: "Each statement is attributed to the source book it came from." },
    { label: "Grounding verify", detail: "Audits claims against the sources and sets a confidence badge; advisory, never blocks the answer." },
    { label: "Configurable pipeline", detail: "Swap the model used at each LLM stage in the diagram below." },
  ],
} as const;
