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
 *  Both share the pipeline shape; only the map-node note differs by mode.
 *  The `clarify` node is a terminal side-branch (parse → clarify on ambiguity)
 *  and is rendered as a footnote rather than in the linear chain. */
export default function ChapterPipelineDiagram({
  mode, providers, stageModels, onStageModelChange,
}: ChapterPipelineDiagramProps) {
  const mapNote = mode === "facilitate" ? "teach each section" : "compress each section";
  // Exclude terminal branch nodes from the linear FlowDiagram chain.
  const clarifyNode = CHAPTER_PIPELINE.nodes.find((n) => n.id === "clarify");
  const nodes: FlowNode[] = CHAPTER_PIPELINE.nodes
    .filter((n) => n.id !== "clarify")
    .map((n) => ({
      id: n.id,
      label: n.label,
      desc: n.id === "map" ? `${n.desc} (${mapNote})` : n.desc,
      kind: n.kind,
      defaultModel: n.defaultModel,
    }));
  return (
    <div>
      <FlowDiagram
        nodes={nodes}
        inputLabel="Chapter + subtopics"
        outputLabel="Chapter digest"
        providers={providers}
        stageModels={stageModels}
        onStageModelChange={onStageModelChange}
      />
      {clarifyNode && (
        <div className="flow__branch-note" data-node="clarify">
          <span className="flow__branch-label">⤷ {clarifyNode.label}:</span>{" "}
          <span className="flow__branch-desc">{clarifyNode.desc}</span>
        </div>
      )}
    </div>
  );
}
