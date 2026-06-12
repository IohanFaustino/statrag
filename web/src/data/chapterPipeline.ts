// Static description of the chapter pipeline (facilitate + resume) for the
// mode's (i) modal. Mirrors src/services/chat/agents/chapter.py::run_chapter.
// Both modes share this diagram; only node-label copy verbosity differs.

export interface ChapterNode {
  id: "parse" | "fetch" | "resolve" | "map" | "stitch" | "ground" | "clarify" | "retrieve" | "teach" | "verify" | "write" | "bind";
  label: string;
  desc: string;
  kind: "llm" | "data";
  defaultModel: string;
}

export interface ChapterEdge {
  from: string;
  to: string;
}

export const CHAPTER_PIPELINE: { nodes: ChapterNode[]; edges: ChapterEdge[] } = {
  nodes: [
    {
      id: "parse",
      label: "Parse + resolve scope",
      desc: "Matches your request to a known book (fuzzy title/author), normalises the chapter, and expands section ranges — using the book catalog.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "fetch",
      label: "Fetch chapter",
      desc: "Pulls every section of the chapter from Qdrant and sorts them in reading order (by page). No search — structural fetch.",
      kind: "data",
      defaultModel: "qdrant scroll (book + chapter filter)",
    },
    {
      id: "resolve",
      label: "Resolve subtopics",
      desc: "Maps the subtopics you asked for to the chapter's real headings (closest-match + confirm). Empty = whole chapter.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "map",
      label: "Per-section pass",
      desc: "Walks the selected sections in order; teaches each (facilitate) or compresses each (resume), threading a running context so ideas build as the author intended.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "stitch",
      label: "Stitch",
      desc: "Adds a short intro and outro. Never reorders the sections.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "ground",
      label: "Ground check",
      desc: "Audits the digest against the sources and sets the grounding badge. Advisory — never blocks the output.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "clarify",
      label: "Clarify (if ambiguous)",
      desc: "If the book is unknown or ambiguous, or the chapter doesn't exist, the run stops and asks you to pick — candidate chips + a short message. A confident match skips this.",
      kind: "data",
      defaultModel: "—",
    },
  ],
  edges: [
    { from: "parse", to: "clarify" },
    { from: "parse", to: "fetch" },
    { from: "fetch", to: "resolve" },
    { from: "resolve", to: "map" },
    { from: "map", to: "stitch" },
    { from: "stitch", to: "ground" },
  ],
};

/** Separate pipeline for the facilitate modal — single-section story pipeline.
 *  Teaches exactly ONE section per request: concept-map → story (hook/movements/takeaway)
 *  → pure-code bind → pure-code fidelity verify. Resume keeps CHAPTER_PIPELINE. */
export const FACILITATE_PIPELINE: { nodes: ChapterNode[]; edges: ChapterEdge[] } = {
  nodes: [
    {
      id: "parse",
      label: "Parse + resolve scope",
      desc: "Matches your request to a known book (fuzzy title/author) and normalises the chapter using the book catalog. Emits a clarify event if the book is ambiguous.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "fetch",
      label: "Fetch section",
      desc: "Resolves exactly ONE section via closest-match + confirm against the chapter's headings, then pulls that single section from Qdrant. No loop — facilitate teaches one section per request.",
      kind: "data",
      defaultModel: "qdrant (one-section)",
    },
    {
      id: "map",
      label: "Concept map",
      desc: "Extract key concepts, theorems, and formulas from the section as [[cN]] anchors, flagging each as concept / theorem / formula.",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "write",
      label: "Write story",
      desc: "Write the section as a connected story: hook → movements → takeaway. Formal statements (definition / lemma / theorem / proposition / corollary / remark) are reproduced VERBATIM then unpacked didactically (elements → associations → intuition → concise close).",
      kind: "llm",
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "bind",
      label: "Bind · pure code",
      desc: "Attach concept provenance and 📕 corpus citations verbatim from retrieval payloads. Strips any [[cN]] anchor the writer invented that has no matching concept entry — never model-authored citation text.",
      kind: "data",
      defaultModel: "pure code",
    },
    {
      id: "verify",
      label: "Verify grounding",
      desc: "Pure-code statement fidelity: checks each formal statement is reproduced verbatim by token-recall against the source section. Sets the grounding badge. NOT an LLM call.",
      kind: "data",
      defaultModel: "pure code (statement fidelity)",
    },
    {
      id: "clarify",
      label: "Clarify (if ambiguous)",
      desc: "If the book is unknown / ambiguous, or the section cannot be resolved, the run stops and asks you to pick. A confident match skips this.",
      kind: "data",
      defaultModel: "—",
    },
  ],
  edges: [
    { from: "parse", to: "clarify" },
    { from: "parse", to: "fetch" },
    { from: "fetch", to: "map" },
    { from: "map", to: "write" },
    { from: "write", to: "bind" },
    { from: "bind", to: "verify" },
  ],
};
