// Description of the Tutor mode itself (the modal opens from the Tutor card).
// What it is, what it was designed for, and its features.

export const TUTOR_MODE = {
  title: "Tutor mode",
  blurb: "Structured, source-grounded tutoring",
  description:
    "Tutor mode answers a statistics / econometrics / machine-learning question with a structured, textbook-quality explanation built only from the indexed books. Instead of one block of prose, it synthesizes the retrieved sources into labelled aspects so a technical learner can move from a quick answer to the formal result, the intuition, a worked example, and the caveats — every claim traceable to its source.",
  features: [
    { label: "Multi-aspect answer", detail: "Introduction, Definition, Formal statement (definition/theorem/proposition when sources provide one, rendered as labelled blockquotes with citation), Example & Intuition, Applications, Further reading." },
    { label: "Per-claim citations", detail: "Each statement is attributed to the book it came from; multi-source paragraphs are split per source." },
    { label: "Verbatim theorems", detail: "Reproduces a source's stated definition/theorem word-for-word when available (formal_statements[] with kind, label, statement, cite), else an indirect citation." },
    { label: "Relevant figures", detail: "Figures are retrieved and judged for relevance, then placed inline next to the aspect they illustrate." },
    { label: "Example & further-reading audit", detail: "Checks the worked example actually illustrates the concept and suggests open research questions." },
    { label: "Configurable pipeline", detail: "Swap the model used at each LLM stage in the diagram below." },
  ],
} as const;
