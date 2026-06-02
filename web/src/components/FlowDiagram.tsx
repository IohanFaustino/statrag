import NodeModelDropdown from "./NodeModelDropdown";
import type { ModelProvider } from "../types";

export interface FlowNode {
  id: string;
  label: string;
  desc: string;
  kind: "llm" | "data";
  /** per-stage model override key; defaults to id. */
  stageKey?: string;
  defaultModel: string;
}

interface FlowDiagramProps {
  nodes: FlowNode[];
  inputLabel: string;
  outputLabel: string;
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onStageModelChange(stage: string, modelId: string): void;
}

/** Centered down-arrow connector between two flow nodes. */
function Connector() {
  return (
    <div className="flow__arrow" aria-hidden="true">
      <svg viewBox="0 0 12 26" width="12" height="26" fill="none"
        stroke="var(--text-tertiary, #888)" strokeWidth="1.4">
        <path d="M6 0 V20" strokeOpacity="0.55" />
        <path d="M2 16 L6 21 L10 16" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.85" />
      </svg>
    </div>
  );
}

/** Generic vertical flow-graph for a linear pipeline. Reuses the tutor
 *  `pipe2` node visual language: dashed io boxes top/bottom, llm/data node
 *  boxes joined by centered down-arrow connectors. Each llm node carries a
 *  per-stage model dropdown; data nodes show a fixed model label. */
export default function FlowDiagram({
  nodes, inputLabel, outputLabel, providers, stageModels, onStageModelChange,
}: FlowDiagramProps) {
  return (
    <div className="pipe2 flow" role="group" aria-label="Pipeline — input to output">
      <div className="pipe2__node pipe2__node--io flow__node">
        <div className="pipe2__node-hd"><span className="pipe2__node-label">{inputLabel}</span></div>
      </div>
      {nodes.map((n) => {
        const stage = n.stageKey ?? n.id;
        const activeId = stageModels[stage] ?? n.defaultModel;
        return (
          <div key={n.id} className="flow__seg">
            <Connector />
            <div className={"pipe2__node flow__node pipe2__node--" + n.kind}>
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
                {n.kind === "llm"
                  ? <span className="pipe2__badge" title="Click the model to swap">swap</span>
                  : <span className="pipe2__badge pipe2__badge--data" title="Fixed data stage">data</span>}
              </div>
              <div className="pipe2__node-desc">{n.desc}</div>
              {n.kind === "llm" ? (
                <NodeModelDropdown
                  value={activeId}
                  providers={providers}
                  onChange={(id) => onStageModelChange(stage, id)}
                />
              ) : (
                <span className="pipe2__model-fixed">{n.defaultModel}</span>
              )}
            </div>
          </div>
        );
      })}
      <Connector />
      <div className="pipe2__node pipe2__node--io flow__node">
        <div className="pipe2__node-hd"><span className="pipe2__node-label">{outputLabel}</span></div>
      </div>
    </div>
  );
}
