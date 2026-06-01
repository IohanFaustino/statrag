import { QA_PIPELINE } from "../data/qaPipeline";
import NodeModelDropdown from "./NodeModelDropdown";
import type { ModelProvider } from "../types";

interface QAPipelineDiagramProps {
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
}

/** Editable Q&A pipeline diagram for the mode's (i) modal. Each LLM node
 *  carries a per-stage model dropdown writing stageModels[node.id]. */
export default function QAPipelineDiagram({
  providers,
  stageModels,
  onStageModelChange,
}: QAPipelineDiagramProps) {
  return (
    <div className="qa-pipeline">
      <ol className="qa-pipeline__nodes">
        {QA_PIPELINE.nodes.map((n) => {
          const activeId = stageModels[n.id] ?? n.defaultModel;
          return (
            <li key={n.id} className={"qa-pipeline__node qa-pipeline__node--" + n.kind}>
              <div className="qa-pipeline__label">{n.label}</div>
              <div className="qa-pipeline__desc">{n.desc}</div>
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
