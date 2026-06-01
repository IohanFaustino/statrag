import { QA_PIPELINE } from "../data/qaPipeline";
import FlowDiagram, { type FlowNode } from "./FlowDiagram";
import type { ModelProvider } from "../types";

interface QAPipelineDiagramProps {
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
}

const QA_NODES: FlowNode[] = QA_PIPELINE.nodes.map((n) => ({
  id: n.id, label: n.label, desc: n.desc, kind: n.kind, defaultModel: n.defaultModel,
}));

/** Editable Q&A pipeline graph for the mode's (i) modal. */
export default function QAPipelineDiagram({ providers, stageModels, onStageModelChange }: QAPipelineDiagramProps) {
  return (
    <FlowDiagram
      nodes={QA_NODES}
      inputLabel="Question"
      outputLabel="Answer"
      providers={providers}
      stageModels={stageModels}
      onStageModelChange={onStageModelChange}
    />
  );
}
