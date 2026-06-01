import { CHAPTER_PIPELINE, FACILITATE_PIPELINE } from "../data/chapterPipeline";
import type { ChapterNode, ChapterEdge } from "../data/chapterPipeline";
import FlowDiagram, { type FlowNode } from "./FlowDiagram";
import type { ModelProvider } from "../types";

interface ChapterPipelineDiagramProps {
  mode: "facilitate" | "resume";
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
  /** Override the pipeline data. Defaults to CHAPTER_PIPELINE (resume) or
   *  FACILITATE_PIPELINE (facilitate) based on the mode prop. */
  pipeline?: { nodes: ChapterNode[]; edges: ChapterEdge[] };
}

/** Editable chapter pipeline graph, shared by the facilitate + resume modals.
 *  Resume uses CHAPTER_PIPELINE; facilitate uses FACILITATE_PIPELINE by default.
 *  The `clarify` node is a terminal side-branch (parse → clarify on ambiguity)
 *  and is rendered as a footnote rather than in the linear chain. */
export default function ChapterPipelineDiagram({
  mode, providers, stageModels, onStageModelChange, pipeline,
}: ChapterPipelineDiagramProps) {
  const activePipeline = pipeline ?? (mode === "facilitate" ? FACILITATE_PIPELINE : CHAPTER_PIPELINE);
  const mapNote = mode === "facilitate" ? "teach each section" : "compress each section";
  // Exclude terminal branch nodes from the linear FlowDiagram chain.
  const clarifyNode = activePipeline.nodes.find((n) => n.id === "clarify");
  const nodes: FlowNode[] = activePipeline.nodes
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
