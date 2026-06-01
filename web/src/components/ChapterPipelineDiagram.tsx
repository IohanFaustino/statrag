import { CHAPTER_PIPELINE } from "../data/chapterPipeline";
import NodeModelDropdown from "./NodeModelDropdown";
import type { ModelProvider } from "../types";

interface ChapterPipelineDiagramProps {
  mode: "facilitate" | "resume";
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
}

/** Editable chapter pipeline diagram, shared by the facilitate + resume
 *  modals. Both modes share the diagram shape; only the map-node note differs. */
export default function ChapterPipelineDiagram({
  mode,
  providers,
  stageModels,
  onStageModelChange,
}: ChapterPipelineDiagramProps) {
  const mapNote = mode === "facilitate" ? "teach each section" : "compress each section";
  return (
    <div className="qa-pipeline">
      <ol className="qa-pipeline__nodes">
        {CHAPTER_PIPELINE.nodes.map((n) => {
          const activeId = stageModels[n.id] ?? n.defaultModel;
          return (
            <li key={n.id} className={"qa-pipeline__node qa-pipeline__node--" + n.kind}>
              <div className="qa-pipeline__label">{n.label}</div>
              <div className="qa-pipeline__desc">{n.desc}</div>
              {n.id === "map" && <div className="qa-pipeline__sub">{mapNote}</div>}
              {n.kind === "llm" ? (
                <NodeModelDropdown
                  value={activeId}
                  providers={providers}
                  onChange={(id) => onStageModelChange(n.id, id)}
                />
              ) : (
                <div className="qa-pipeline__model">{n.defaultModel}</div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
