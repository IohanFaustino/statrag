import { QA_PIPELINE } from "../data/qaPipeline";
import FlowDiagram, { type FlowNode } from "./FlowDiagram";
import type { ModelProvider } from "../types";

interface QAPipelineDiagramProps {
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
}

// Exclude the terminal clarify branch from the linear chain.
const QA_NODES: FlowNode[] = QA_PIPELINE.nodes
  .filter((n) => n.id !== "clarify")
  .map((n) => ({
    id: n.id, label: n.label, desc: n.desc, kind: n.kind, defaultModel: n.defaultModel,
  }));

const CLARIFY_NODE = QA_PIPELINE.nodes.find((n) => n.id === "clarify");

/** Editable Q&A pipeline graph for the mode's (i) modal.
 *  The `clarify` node is a terminal side-branch (scope → clarify on ambiguity)
 *  and is rendered as a footnote rather than in the linear chain. */
export default function QAPipelineDiagram({ providers, stageModels, onStageModelChange }: QAPipelineDiagramProps) {
  return (
    <div>
      <FlowDiagram
        nodes={QA_NODES}
        inputLabel="Question"
        outputLabel="Answer"
        providers={providers}
        stageModels={stageModels}
        onStageModelChange={onStageModelChange}
      />
      {CLARIFY_NODE && (
        <div className="flow__branch-note" data-node="clarify">
          <span className="flow__branch-label">⤷ {CLARIFY_NODE.label}:</span>{" "}
          <span className="flow__branch-desc">{CLARIFY_NODE.desc}</span>
        </div>
      )}
    </div>
  );
}
