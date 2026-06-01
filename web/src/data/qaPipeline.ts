// Static description of the punctual Q&A pipeline for the mode's (i) modal.
// Mirrors src/services/chat/agents/qa.py::run_qa. Read-only (Q&A model
// override is via Settings, not per-node clickable like the tutor diagram).

export interface QANode {
  id: "scope" | "retrieve" | "generate" | "verify" | "clarify";
  label: string;
  desc: string;
  kind: "llm" | "data";
  defaultModel: string;
}

export interface QAEdge {
  from: string;
  to: string;
}

export const QA_PIPELINE: { nodes: QANode[]; edges: QAEdge[] } = {
  nodes: [
    {
      id: "scope",
      label: "Scope extract + resolve book",
      desc: "Parses your question into {target gap, what you already know, answer form} so generation answers only the gap. Also fuzzy-matches the book/author if you named one — resolves it against the catalog before retrieval.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "retrieve",
      label: "Hybrid retrieval",
      desc: "Dense (embeddings) + sparse (BM25) search over the selected books, reranked. Queries the narrowed gap, not the raw question. Top-k=4 for precision.",
      kind: "data",
      defaultModel: "text-embedding-3-large → RRF + rerank",
    },
    {
      id: "generate",
      label: "Scoped generate",
      desc: "Writes a terse, direct answer grounded in the sources, skipping anything you already said you know.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "verify",
      label: "Grounding verify",
      desc: "Audits each claim against the sources; softens unsupported ones and sets the grounding confidence badge. Advisory — never blocks the answer.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "clarify",
      label: "Clarify (if ambiguous)",
      desc: "If the named book is unknown or ambiguous, the run stops and asks you to pick — candidate chips + a short message. A confident match skips this.",
      kind: "data",
      defaultModel: "—",
    },
  ],
  edges: [
    { from: "scope", to: "clarify" },
    { from: "scope", to: "retrieve" },
    { from: "retrieve", to: "generate" },
    { from: "generate", to: "verify" },
  ],
};
