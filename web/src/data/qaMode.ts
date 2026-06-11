// Description of the Q&A mode itself (the modal opens from the Q&A card).
export const QA_MODE = {
  title: "Q&A mode",
  blurb: "Storytelling answers, source-grounded across corpus + Wikipedia",
  description:
    "Q&A mode answers a single, focused question as a three-act narrative — intro (scene-setter), deepening (core explanation), conclusion (take-away). It narrows your question to the actual gap, retrieves a small high-precision set of corpus sources plus relevant Wikipedia articles, writes a storytelling answer with [n] citation markers bound by a pure-code binder, and audits each claim for grounding.",
  features: [
    { label: "Gap-scoped", detail: "Parses your question into {target gap, assumed-known, answer form, Wikipedia terms} so it answers only what's missing." },
    { label: "Corpus + Wikipedia", detail: "Hybrid dense + sparse corpus retrieval runs in parallel with Wikipedia fetch, giving both textbook depth and encyclopaedic context." },
    { label: "Storytelling narrative", detail: "Writes intro → deepening → conclusion: a three-act structure that reads as connected prose, not a list of facts." },
    { label: "Pure-code citation binder", detail: "[[eid]] placeholders are rewritten to sequential [n] markers by deterministic code — no model hallucination in the citation list." },
    { label: "Grounding verify", detail: "Audits claims against the sources and sets a confidence badge; advisory, never blocks the answer." },
    { label: "Configurable pipeline", detail: "Swap the model used at each LLM stage (scope, write, verify) in the diagram below." },
  ],
} as const;
