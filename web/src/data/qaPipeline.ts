// Static description of the Q&A storytelling pipeline for the mode's (i) modal.
// Mirrors src/services/chat/agents/qa.py::run_qa. Read-only (Q&A model
// override is via Settings, not per-node clickable like the tutor diagram).

export interface QANode {
  id: "scope" | "retrieve" | "write" | "bind" | "verify" | "clarify";
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
      desc: "Parses your question into {target gap, what you already know, answer form, Wikipedia terms} so generation answers only the gap. Also fuzzy-matches the book/author if you named one — resolves it against the catalog before retrieval.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "retrieve",
      label: "Hybrid retrieval — corpus ∥ wiki",
      desc: "Dense (embeddings) + sparse (BM25) search over the selected books (corpus) and Wikipedia (wiki) in parallel, reranked. Queries the narrowed gap. Top-k=4 corpus for precision; Wikipedia articles fetched for scoped wiki_terms.",
      kind: "data",
      defaultModel: "text-embedding-3-large → RRF + rerank ∥ Wikipedia",
    },
    {
      id: "write",
      label: "Story writer — intro → deepening → conclusion",
      desc: "Writes a storytelling narrative in three acts: intro (scene-setter), deepening (core explanation with [[eid]] citation markers for both corpus and Wikipedia sources), conclusion (take-away). Grounded in retrieved corpus + Wikipedia context.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "bind",
      label: "Citation binder (pure code)",
      desc: "Pure-code pass: rewrites [[eid]] placeholders in the story prose to sequential [n] markers (1-based) and builds the authoritative StoryCitation list from verbatim retrieval payload. No model — deterministic and exact.",
      kind: "data",
      defaultModel: "—",
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
    { from: "retrieve", to: "write" },
    { from: "write", to: "bind" },
    { from: "bind", to: "verify" },
  ],
};
