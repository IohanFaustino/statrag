// Static description of the chapter pipeline (facilitate + resume) for the
// mode's (i) modal. Mirrors src/services/chat/agents/chapter.py::run_chapter.
// Both modes share this diagram; only node-label copy verbosity differs.

export interface ChapterNode {
  id: "parse" | "fetch" | "resolve" | "map" | "stitch" | "ground" | "clarify";
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
