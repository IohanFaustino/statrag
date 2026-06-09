import FlowDiagram, { type FlowNode } from "./FlowDiagram";

// Static node list for the Extension mode topology-C pipeline.
// Mirrors src/services/chat/agents/extension_runner.py round stages.
const EXTENSION_NODES: FlowNode[] = [
  {
    id: "resolve",
    label: "Resolve + confirm",
    desc: "Fuzzy-matches the requested book/chapter against the catalog and confirms scope before loading structure. Stops and clarifies if the target is ambiguous.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "fetch",
    label: "Fetch structure",
    desc: "Qdrant scroll with book + chapter filter — returns the ordered section list without downloading full chunk text yet.",
    kind: "data",
    defaultModel: "qdrant scroll (book + chapter filter)",
  },
  {
    id: "analyst",
    label: "Analyst (per section)",
    desc: "One analyst subagent per section: retrieves the full chunk, extracts key concepts and formulas, and produces a structured section note.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "polish",
    label: "Polish (curate timeline)",
    desc: "Merges section notes into a coherent chapter timeline, drops duplicates, and emits a gap list for augmentation.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "augmentor",
    label: "Augmentor (corpus + Wikipedia)",
    desc: "For each gap in the timeline, fires hybrid corpus retrieval and a Wikipedia lookup in parallel, then merges the results into the draft.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "judge",
    label: "Judge (loop, capped)",
    desc: "Audits the augmented digest for formula completeness and citation coverage. If gaps remain and the iteration cap is not hit, re-runs the augmentor; otherwise emits the final ExtensionDigest.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
];

/** Read-only Extension pipeline graph for the mode's (i) modal.
 *  No per-stage model dropdowns — model overrides for Extension are handled
 *  via the global model picker, not per-node. */
export default function ExtensionPipelineDiagram() {
  return (
    <FlowDiagram
      nodes={EXTENSION_NODES}
      inputLabel="Book + chapter"
      outputLabel="Extension digest"
      providers={[]}
      stageModels={{}}
      onStageModelChange={() => {}}
    />
  );
}
