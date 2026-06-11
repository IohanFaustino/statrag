// Static description of the tutor (deep-tutor) pipeline for the About-model
// diagram. Mirrors the stage sequence in
// src/services/chat/agents/deep_tutor.py::run_deep_tutor.
//
// Only nodes with a non-null `stage` are model-overridable (clickable to swap
// to a picker chat model). Locked nodes use a fixed model class (embedding /
// cross-encoder / vision) that a chat model cannot replace.

export type StageKey = "expansion" | "draft" | "image_judge" | "vision_explain" | "plan";

export interface PipelineNode {
  id: string;
  label: string;
  desc: string;
  kind: "io" | "llm" | "data";
  // Override key when this node's model can be swapped; null when locked.
  stage: StageKey | null;
  // Display string for the default model. "__active__" = follows the picker.
  defaultModel: string;
  locked: boolean;
}

export interface PipelineEdge {
  from: string;
  to: string;
}

export const TUTOR_PIPELINE: { nodes: PipelineNode[]; edges: PipelineEdge[] } = {
  nodes: [
    {
      id: "input",
      label: "Question",
      desc: "Your query enters the pipeline.",
      kind: "io",
      stage: null,
      defaultModel: "",
      locked: true,
    },
    {
      id: "expansion",
      label: "Query planner",
      desc: "Interprets the question. Default: one nano call → concepts, queries, facets. With TUTOR_PLANNER_CHAIN=1: a 3-step prompt chain — decompose (question → atomic sub-questions) → expand (per sub-question: concept, query, facet) → consolidate (dedupe, budget perspectives) → QueryPlan.",
      kind: "llm",
      stage: "expansion",
      defaultModel: "gpt-5.4-nano-2026-03-17",
      locked: false,
    },
    {
      id: "retrieval",
      label: "Hybrid retrieval ×N",
      desc: "Dense (embeddings) + sparse (BM25) search over book collections, running N queries in parallel and merging results via RRF.",
      kind: "data",
      stage: null,
      defaultModel: "text-embedding-3-large → RRF",
      locked: true,
    },
    {
      id: "rerank",
      label: "Density select + rerank + adjacent sections",
      desc: "Cross-encoder reranking and density-based section selection. Also pulls relevant adjacent (sibling) sections, gated by the cross-encoder rerank.",
      kind: "data",
      stage: null,
      defaultModel: "cross-encoder",
      locked: true,
    },
    {
      id: "diversity",
      label: "Author diversity",
      desc: "Selects sections spanning multiple authors (author + year) so the answer can compare/synthesize perspectives.",
      kind: "data",
      stage: null,
      defaultModel: "",
      locked: false,
    },
    {
      id: "coverage",
      label: "Coverage check",
      desc: "Grades the selected sources against the planner's facets and re-queries any missing facet (e.g. ensures both the bias AND variance formula were retrieved).",
      kind: "data",
      stage: null,
      locked: true,
      defaultModel: "facet re-query",
    },
    {
      id: "image_judge",
      label: "Figure judge (T1)",
      desc: "Caption-level judge that decides which figures to include.",
      kind: "llm",
      stage: "image_judge",
      defaultModel: "gpt-5.4-nano-2026-03-17",
      locked: false,
    },
    {
      id: "plan",
      label: "Planner",
      desc: "Plans the answer: a single thesis throughline plus explicit author contrasts the narrative develops. One agent. Skipped when the planner rates the question simple (perspectives ≤ 1).",
      kind: "llm",
      stage: "plan",
      locked: false,
      defaultModel: "gpt-5.4-nano-2026-03-17",
    },
    {
      id: "draft",
      label: "Narrative draft",
      desc: "Writes the structured multi-aspect answer as a single narrative pass. The main model.",
      kind: "llm",
      stage: "draft",
      defaultModel: "__active__",
      locked: false,
    },
    {
      id: "vision_explain",
      label: "Vision explain",
      desc: "Reads each placed figure with a vision model (on by default). Pick any chat model; a non-vision model falls back to the caption.",
      kind: "llm",
      stage: "vision_explain",
      defaultModel: "gpt-4o-mini",
      locked: false,
    },
    {
      id: "output",
      label: "Answer",
      desc: "Structured tutor answer streamed to the UI.",
      kind: "io",
      stage: null,
      defaultModel: "",
      locked: true,
    },
  ],
  // Vertical chain: question → query planner → hybrid retrieval → … → answer.
  // Coverage check has a loop-back re-query edge back to retrieval (cap 1).
  edges: [
    { from: "input",      to: "expansion" },
    { from: "expansion",  to: "retrieval" },
    { from: "retrieval",  to: "rerank" },
    { from: "rerank",     to: "diversity" },
    { from: "diversity",  to: "coverage" },
    { from: "coverage",   to: "retrieval" },
    { from: "coverage",   to: "image_judge" },
    { from: "image_judge", to: "plan" },
    { from: "plan",       to: "draft" },
    { from: "draft",      to: "vision_explain" },
    { from: "vision_explain", to: "output" },
  ],
};
