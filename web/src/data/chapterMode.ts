// Descriptions of the two chapter modes (modals open from the Facilitate /
// Resume cards). Both share the chapter pipeline; framing differs.
export const FACILITATE_MODE = {
  title: "Facilitate mode",
  blurb: "One-section story — hook, movements, takeaway",
  description:
    "Facilitate mode teaches exactly one section per request as a connected narrative: a hook that frames the topic, movements that develop it (with formal statements reproduced verbatim and unpacked didactically), and a takeaway. Concept anchors are assigned to key terms and theorems; clicking one opens a corpus + Wikipedia side-chat for deeper exploration. Pure-code binding and statement-fidelity checking ensure citations and formal statements are never model-authored.",
  features: [
    { label: "One section per request", detail: "Focuses on exactly one section — resolved via closest-match + confirm against the chapter's headings. No section loop." },
    { label: "Connected story (hook → movements → takeaway)", detail: "The section is narrated as a story arc rather than a list of bullet points or an expansion." },
    { label: "Verbatim formal statements unpacked", detail: "Definitions, lemmas, theorems, propositions, corollaries, and remarks are reproduced verbatim from the source, then unpacked: elements → associations → intuition → concise close." },
    { label: "Concept anchors (clickable pills)", detail: "Key concepts and formulas become [[cN]] anchors rendered as clickable pills; each pill opens a ConceptChat side panel with corpus + Wikipedia answers." },
    { label: "Pure-code bind + fidelity verify", detail: "Concept provenance and citations are assembled by pure code from retrieval payloads — the model never writes citation text. Statement fidelity is checked by token-recall, not an LLM call." },
    { label: "Grounding badge", detail: "The pure-code fidelity pass sets the grounding badge based on how well formal statements match the source section." },
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
