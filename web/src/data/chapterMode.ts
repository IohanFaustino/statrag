// Descriptions of the two chapter modes (modals open from the Facilitate /
// Resume cards). Both share the chapter pipeline; framing differs.
export const FACILITATE_MODE = {
  title: "Facilitate mode",
  blurb: "Concept map + plain-language key points",
  description:
    "Facilitate mode builds a concept map of each section, teaches it in simpler language as short paragraphs and bullet key points (not an expansion), and turns referenced concepts and step-bearing formulas into clickable anchors. Each anchor is backed by same-author-first sub-retrieval — the explanation appears in a modal pop-up and as a footnote on export.",
  features: [
    { label: "Concept map", detail: "Extracts key points and concepts/theorems/formulas per section, flagging which are defined here vs only referenced." },
    { label: "Key points (filtered, not expanded)", detail: "Bullet key points are distilled from the section — not elaborated or padded beyond the source." },
    { label: "Plain language", detail: "Each section is rewritten as short, readable paragraphs while preserving technical precision." },
    { label: "Clickable concepts (modal + footnote on export)", detail: "Referenced concepts become [[concept]] anchors that open a definition modal; footnotes are added on PDF/markdown export." },
    { label: "Same-author sub-retrieval", detail: "Concept explanations prefer the same author and the nearest prior section; other authors are a fallback only." },
    { label: "Grounded + verify", detail: "Audits the rewritten body against the sources and sets the grounding badge. Advisory — never blocks the output." },
  ],
} as const;

export const RESUME_MODE = {
  title: "Resume mode",
  blurb: "Ordered compressed recap",
  description:
    "Resume mode condenses a whole chapter (or chosen subtopics) into a compact recap that follows the author's reading order. It fetches every section structurally — no relevance search — then compresses each section in turn so you get a faithful, ordered summary.",
  features: [
    { label: "Structural fetch", detail: "Pulls the chapter's sections from Qdrant by book+chapter filter, ordered by page — not by relevance." },
    { label: "Reading-order preserved", detail: "Sections are never reordered; the recap follows the chapter's own sequence." },
    { label: "Subtopic resolve", detail: "Matches your book/chapter/sections even when named loosely; asks you to confirm only if it's ambiguous." },
    { label: "Compress each section", detail: "Per-section compact pass keeping the key result of each part." },
    { label: "Grounded + stitched", detail: "Adds a short intro/outro and audits the recap against the sources." },
    { label: "Configurable pipeline", detail: "Swap the model used at each LLM stage in the diagram below." },
  ],
} as const;
