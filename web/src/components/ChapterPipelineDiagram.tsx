import { CHAPTER_PIPELINE } from "../data/chapterPipeline";
import FlowDiagram, { type FlowNode } from "./FlowDiagram";
import type { ModelProvider } from "../types";

interface ChapterPipelineDiagramProps {
  mode: "facilitate" | "resume";
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
}

/** Editable chapter pipeline graph, shared by the facilitate + resume modals.
 *  Both share the pipeline shape; only the map-node note differs by mode. */
export default function ChapterPipelineDiagram({
  mode, providers, stageModels, onStageModelChange,
}: ChapterPipelineDiagramProps) {
  const mapNote = mode === "facilitate" ? "teach each section" : "compress each section";
  const nodes: FlowNode[] = CHAPTER_PIPELINE.nodes.map((n) => ({
    id: n.id,
    label: n.label,
    desc: n.id === "map" ? `${n.desc} (${mapNote})` : n.desc,
    kind: n.kind,
    defaultModel: n.defaultModel,
  }));
  return (
    <FlowDiagram
      nodes={nodes}
      inputLabel="Chapter + subtopics"
      outputLabel="Chapter digest"
      providers={providers}
      stageModels={stageModels}
      onStageModelChange={onStageModelChange}
    />
  );
}
