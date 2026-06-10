import FlowDiagram, { type FlowNode } from "./FlowDiagram";

// Static node list for the Extension mode topology-C pipeline.
// Mirrors src/services/chat/agents/extension_runner.py round stages.
const EXTENSION_NODES: FlowNode[] = [
  {
    id: "resolve",
    label: "Resolve + confirm",
    desc: "Fuzzy-matches the requested book/chapter against the catalog. Uses embedding fallback (hybrid_search) when exact title match fails. Stops and clarifies if the target is ambiguous.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "fetch",
    label: "Fetch structure",
    desc: "Qdrant scroll with book + chapter filter — returns the ordered section list (up to 2500 chars/section). Fuzzy subtopic filter narrows to requested sections if specified.",
    kind: "data",
    defaultModel: "qdrant scroll (book + chapter filter)",
  },
  {
    id: "analyst",
    label: "Analyst (per section)",
    desc: "One analyst subagent per section. Classifies gaps using 4-type taxonomy: [FORMAL-DEF] undefined concept, [FORMULA-DERIV] missing derivation, [COMPARATIVE] no cross-book context, [APPLICATION] no worked example. Requires ≥ 2 gaps per section.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "polish",
    label: "Polish (curate timeline)",
    desc: "Merges section notes into a coherent chapter timeline. Preserves formal definitions, key formulas, and notation — does not summarise. Drops only exercises, worked solutions, and redundant restatements.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "augmentor",
    label: "Augmentor (corpus + Wikipedia)",
    desc: "For each gap query: retrieves from other books (top_k=10, cross-round dedup) and Wikipedia (with disambiguation fallback). Scores relevance 1–5; discards score 1–2; writes footnote ≥ 40 words for score 3–5. Marks each query done|unfilled.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "judge",
    label: "Judge (loop, capped)",
    desc: "Parses COVERAGE markers, merges orphan footnotes by title similarity, verifies all fields are in English. If any non-trivial point has 0 footnotes, re-delegates augmentor before emitting the final ExtensionDigest.",
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
