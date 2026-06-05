// Single source of truth: classify any pipeline node id (tutor / qa / chapter)
// into a functional phase, used for color-grouping in the mode-modal diagrams.

export type Phase = "io" | "planning" | "retrieval" | "generation" | "vision";

export interface PhaseMeta {
  label: string; // short chip text shown in the node header
}

export const PHASE_META: Record<Phase, PhaseMeta> = {
  io:         { label: "I/O" },
  planning:   { label: "PLAN" },
  retrieval:  { label: "RETRIEVAL" },
  generation: { label: "GENERATION" },
  vision:     { label: "VISION" },
};

// Explicit id → phase. Covers tutor (tutorPipeline.ts + orchestrator cluster),
// qa (qaPipeline.ts), and chapter (chapterPipeline.ts) node ids.
export const PHASE_OF: Record<string, Phase> = {
  // tutor — io
  input: "io", output: "io",
  // tutor — planning
  expansion: "planning", plan: "planning",
  // tutor — retrieval
  retrieval: "retrieval", rerank: "retrieval", diversity: "retrieval", coverage: "retrieval",
  // tutor — generation (incl. orchestrator cluster)
  drafting: "generation", draft: "generation", orchestrator: "generation",
  worker1: "generation", worker2: "generation", worker3: "generation", synthesizer: "generation",
  // tutor — vision
  image_judge: "vision", formula_recovery: "vision", vision_explain: "vision",
  // qa
  scope: "planning", retrieve: "retrieval", generate: "generation", verify: "generation",
  clarify: "planning",
  // chapter (facilitate / resume)
  parse: "planning", fetch: "retrieval", resolve: "planning", map: "planning",
  stitch: "generation", ground: "generation", teach: "generation",
};

export function phaseOf(id: string): Phase {
  return PHASE_OF[id] ?? "generation";
}
