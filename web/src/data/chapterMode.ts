// Descriptions of the two chapter modes (modals open from the Facilitate /
// Resume cards). Both share the chapter pipeline; framing differs.
export const FACILITATE_MODE = {
  title: "Facilitate mode",
  blurb: "Ordered didactic walkthrough",
  description:
    "Facilitate mode teaches a whole chapter (or chosen subtopics) in the author's reading order. It fetches every section structurally — no relevance search — then teaches each section in turn, threading a running context so ideas build exactly as the book intended.",
  features: [
    { label: "Structural fetch", detail: "Pulls the chapter's sections from Qdrant by book+chapter filter, ordered by page — not by relevance." },
    { label: "Reading-order preserved", detail: "Sections are never reordered; the digest follows the chapter's own sequence." },
    { label: "Subtopic resolve", detail: "Maps the subtopics you named to the chapter's real headings (closest-match + confirm); empty = whole chapter." },
    { label: "Teach each section", detail: "Per-section didactic pass with a running context so ideas connect across sections." },
    { label: "Grounded + stitched", detail: "Adds a short intro/outro and audits the digest against the sources." },
    { label: "Configurable pipeline", detail: "Swap the model used at each LLM stage in the diagram below." },
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
    { label: "Subtopic resolve", detail: "Maps the subtopics you named to the chapter's real headings (closest-match + confirm); empty = whole chapter." },
    { label: "Compress each section", detail: "Per-section compact pass keeping the key result of each part." },
    { label: "Grounded + stitched", detail: "Adds a short intro/outro and audits the recap against the sources." },
    { label: "Configurable pipeline", detail: "Swap the model used at each LLM stage in the diagram below." },
  ],
} as const;
