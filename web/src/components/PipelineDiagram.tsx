import type { ModelProvider } from "../types";
import { TUTOR_PIPELINE, type StageKey } from "../data/tutorPipeline";
import NodeModelDropdown from "./NodeModelDropdown";
import NodeChoiceDropdown, { type ChoiceOption, type ChoiceValue } from "./NodeChoiceDropdown";
import type { PipelineNode, PipelineEdge } from "../data/tutorPipeline";

const DIVERSITY_OPTIONS: ChoiceOption[] = [
  { label: "Off",        value: 0 },
  { label: "Auto",       value: "auto" },
  { label: "2 authors",  value: 2 },
  { label: "3 authors",  value: 3 },
  { label: "4 authors",  value: 4 },
  { label: "5 authors",  value: 5 },
  { label: "6 authors",  value: 6 },
];

const WORKFLOW_OPTIONS: ChoiceOption[] = [
  { label: "Single draft",               value: "single" },
  { label: "Orchestrator (per author)",  value: "orchestrator" },
  { label: "Organize (V4-PRO, long-ctx)", value: "organize" },
];

interface PipelineDiagramProps {
  pickerModel: string;
  stageModels: Partial<Record<StageKey, string>>;
  providers: ModelProvider[];
  onStageModelChange(stage: StageKey, modelId: string): void;
  diversityAuthors: ChoiceValue;
  onDiversityChange(n: ChoiceValue): void;
  tutorWorkflow: string;
  onWorkflowChange(v: string): void;
}

// Hand-laid layout (px) in a 520×1200 coordinate space. Single vertical column:
// Question → Query planner → Hybrid retrieval ×N → Density select + rerank →
// Author diversity → Coverage check → Figure judge → Planner →
// Drafting workflow → Draft / synthesis → Vision explain → Answer
//
// Coverage check also has a loop-back edge to Hybrid retrieval (left-side arc).
const W = 520;
const BASE_H = 1200;
interface Box { x: number; y: number; w: number; h: number; }

// Row heights and vertical gap between rows.
const GAP = 20;
// Base layout for the "single" workflow — all centred at x=144, w=232.
const CX = 144;    // left edge of centred nodes
const CW = 232;    // width of centred nodes
const BASE_LAYOUT: Record<string, Box> = {
  input:          { x: 160, y: 8,    w: 200, h: 46  },
  expansion:      { x: CX,  y: 82,   w: CW,  h: 92  },
  retrieval:      { x: CX,  y: 194,  w: CW,  h: 66  },
  rerank:         { x: CX,  y: 280,  w: CW,  h: 66  },
  diversity:      { x: CX,  y: 366,  w: CW,  h: 66  },
  coverage:       { x: CX,  y: 452,  w: CW,  h: 66  },
  image_judge:    { x: CX,  y: 538,  w: CW,  h: 92  },
  plan:           { x: CX,  y: 650,  w: CW,  h: 92  },
  drafting:       { x: CX,  y: 762,  w: CW,  h: 66  },
  draft:          { x: CX,  y: 848,  w: CW,  h: 92  },
  vision_explain: { x: CX,  y: 960,  w: CW,  h: 60  },
  output:         { x: 160, y: 1040, w: 200, h: 46  },
};

// Suppresses linting of intentionally-used GAP const
void GAP;

// ── orchestrator cluster geometry ──────────────────────────────────────────
// The `draft` slot starts at y=848. The orchestrator cluster replaces it with:
//   - orchestrator node (same position as draft)
//   - worker row (3 workers side-by-side) below orchestrator
//   - synthesizer below the worker row
// Nodes that follow (vision_explain, output) are shifted down.

const ORCH_Y       = BASE_LAYOUT.draft.y;  // where draft was (848)
const ORCH_H       = 66;
const WORKER_ROW_Y = ORCH_Y + ORCH_H + 18;  // 848
const WORKER_H     = 56;
const SYNTH_Y      = WORKER_ROW_Y + WORKER_H + 18;  // 922
const SYNTH_H      = 66;
const TAIL_SHIFT   = (SYNTH_Y + SYNTH_H) - (BASE_LAYOUT.draft.y + BASE_LAYOUT.draft.h);
// tail shift = how much extra vertical space we added over the single `draft` box.

// Worker layout — three equal columns fitting inside the 232px centre band.
const WORKER_W = 68;
const WORKER_GAP = 6;
const WORKERS_TOTAL_W = 3 * WORKER_W + 2 * WORKER_GAP; // 216
const WORKERS_LEFT_X  = BASE_LAYOUT.draft.x + (BASE_LAYOUT.draft.w - WORKERS_TOTAL_W) / 2; // 152

const ORC_LAYOUT: Record<string, Box> = {
  orchestrator: { x: BASE_LAYOUT.draft.x, y: ORCH_Y,       w: BASE_LAYOUT.draft.w, h: ORCH_H },
  worker1:      { x: WORKERS_LEFT_X,                              y: WORKER_ROW_Y, w: WORKER_W, h: WORKER_H },
  worker2:      { x: WORKERS_LEFT_X + WORKER_W + WORKER_GAP,     y: WORKER_ROW_Y, w: WORKER_W, h: WORKER_H },
  worker3:      { x: WORKERS_LEFT_X + 2 * (WORKER_W + WORKER_GAP), y: WORKER_ROW_Y, w: WORKER_W, h: WORKER_H },
  synthesizer:  { x: BASE_LAYOUT.draft.x, y: SYNTH_Y, w: BASE_LAYOUT.draft.w, h: SYNTH_H },
};

// Extra synthetic nodes for the orchestrator cluster.
const ORC_NODES: PipelineNode[] = [
  {
    id: "orchestrator",
    label: "Orchestrator",
    desc: "Decides subtasks and delegates one per author to parallel workers.",
    kind: "llm",
    stage: "draft",          // shares the `draft` stage model key
    defaultModel: "__active__",
    locked: false,
  },
  {
    id: "worker1",
    label: "Worker",
    desc: "Writes the section for author 1.",
    kind: "llm",
    stage: null,
    defaultModel: "__active__",
    locked: false,
  },
  {
    id: "worker2",
    label: "Worker",
    desc: "Writes the section for author 2.",
    kind: "llm",
    stage: null,
    defaultModel: "__active__",
    locked: false,
  },
  {
    id: "worker3",
    label: "Worker · N",
    desc: "Writes sections for remaining authors.",
    kind: "llm",
    stage: null,
    defaultModel: "__active__",
    locked: false,
  },
  {
    id: "synthesizer",
    label: "Synthesizer",
    desc: "Integrates & compares per-author drafts into the final answer.",
    kind: "llm",
    stage: null,
    defaultModel: "__active__",
    locked: false,
  },
];

// Edges that replace the single `drafting → draft` edge.
const ORC_EDGES: PipelineEdge[] = [
  { from: "drafting",      to: "orchestrator" },
  { from: "orchestrator",  to: "worker1" },
  { from: "orchestrator",  to: "worker2" },
  { from: "orchestrator",  to: "worker3" },
  { from: "worker1",       to: "synthesizer" },
  { from: "worker2",       to: "synthesizer" },
  { from: "worker3",       to: "synthesizer" },
  { from: "synthesizer",   to: "vision_explain" },
];

// IDs that are dashed delegate edges (orchestrator → workers).
const DASHED_EDGES = new Set(["orchestrator→worker1", "orchestrator→worker2", "orchestrator→worker3"]);

// IDs for loop-back edges (go upward; rendered as left-side arcs).
const LOOP_EDGES = new Set(["coverage→retrieval"]);

function buildOrchLayout(): Record<string, Box> {
  const layout: Record<string, Box> = { ...BASE_LAYOUT, ...ORC_LAYOUT };
  // Shift the tail nodes down by TAIL_SHIFT.
  for (const id of ["vision_explain", "output"] as const) {
    layout[id] = { ...BASE_LAYOUT[id], y: BASE_LAYOUT[id].y + TAIL_SHIFT };
  }
  return layout;
}

const ORCH_LAYOUT_FULL = buildOrchLayout();
const ORCH_CANVAS_H = BASE_H + TAIL_SHIFT;

// ──────────────────────────────────────────────────────────────────────────

function modelName(providers: ModelProvider[], id: string): string {
  for (const p of providers) {
    const m = p.models.find((mm) => mm.id === id);
    if (m) return m.name;
  }
  return id;
}

export default function PipelineDiagram({
  pickerModel,
  stageModels,
  providers,
  onStageModelChange,
  diversityAuthors,
  onDiversityChange,
  tutorWorkflow,
  onWorkflowChange,
}: PipelineDiagramProps) {
  const isOrch = tutorWorkflow === "orchestrator";

  // ── Derive effective graph ───────────────────────────────────────────────
  let effectiveNodes: PipelineNode[];
  let effectiveEdges: PipelineEdge[];
  let effectiveLayout: Record<string, Box>;
  let canvasH: number;

  if (!isOrch) {
    effectiveNodes  = TUTOR_PIPELINE.nodes;
    effectiveEdges  = TUTOR_PIPELINE.edges;
    effectiveLayout = BASE_LAYOUT;
    canvasH         = BASE_H;
  } else {
    // Drop `draft` from base nodes; append orchestrator cluster.
    effectiveNodes = [
      ...TUTOR_PIPELINE.nodes.filter((n) => n.id !== "draft"),
      ...ORC_NODES,
    ];
    // Replace `drafting → draft` and `draft → vision_explain` with cluster edges.
    effectiveEdges = [
      ...TUTOR_PIPELINE.edges.filter(
        (e) => !(e.from === "drafting" && e.to === "draft") &&
               !(e.from === "draft"    && e.to === "vision_explain")
      ),
      ...ORC_EDGES,
    ];
    effectiveLayout = ORCH_LAYOUT_FULL;
    canvasH         = ORCH_CANVAS_H;
  }

  // ── Edge path helpers ────────────────────────────────────────────────────
  const edgePath = (fromId: string, toId: string): string => {
    const a = effectiveLayout[fromId];
    const b = effectiveLayout[toId];
    if (!a || !b) return "";
    const sx = a.x + a.w / 2;
    const sy = a.y + a.h;
    const tx = b.x + b.w / 2;
    const ty = b.y;
    const midY = (sy + ty) / 2;
    return `M ${sx} ${sy} C ${sx} ${midY}, ${tx} ${midY}, ${tx} ${ty}`;
  };

  // Loop-back edge: routes out of fromId's LEFT edge, curves up the left
  // margin, and enters toId's LEFT edge. Used for coverage → retrieval.
  const loopBackPath = (fromId: string, toId: string): string => {
    const a = effectiveLayout[fromId];
    const b = effectiveLayout[toId];
    if (!a || !b) return "";
    const MARGIN = 28; // px left of the leftmost node edge
    const sx = a.x;                    // left edge of coverage
    const sy = a.y + a.h / 2;         // mid-height of coverage
    const tx = b.x;                    // left edge of retrieval
    const ty = b.y + b.h / 2;         // mid-height of retrieval
    const lx = Math.min(sx, tx) - MARGIN;  // left margin x
    // Cubic: exit left from coverage, go to margin, travel up, enter retrieval
    return (
      `M ${sx} ${sy} ` +
      `C ${lx} ${sy}, ${lx} ${ty}, ${tx} ${ty}`
    );
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div
      className="pipe2"
      role="group"
      aria-label="Tutor pipeline — input to output"
      style={{ position: "relative", width: W, maxWidth: "100%", height: canvasH, margin: "0 auto", minHeight: canvasH }}
    >
      <svg
        className="pipe2__edges"
        viewBox={`0 0 ${W} ${canvasH}`}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
        aria-hidden="true"
      >
        <defs>
          <marker id="pipe-arrow" markerWidth="8" markerHeight="8" refX="5" refY="4" orient="auto">
            <path d="M0,0 L6,4 L0,8 Z" fill="var(--text-tertiary, #888)" />
          </marker>
          {/* Arrow head for left-pointing loop-back edge (points right, into node left edge) */}
          <marker id="pipe-arrow-right" markerWidth="8" markerHeight="8" refX="1" refY="4" orient="auto">
            <path d="M6,0 L0,4 L6,8 Z" fill="var(--accent-green, #3fb950)" />
          </marker>
        </defs>
        {effectiveEdges.map((e) => {
          const key = `${e.from}-${e.to}`;
          const edgeKey = `${e.from}→${e.to}`;
          const isDashed = DASHED_EDGES.has(edgeKey);
          const isLoop  = LOOP_EDGES.has(edgeKey);

          if (isLoop) {
            const d = loopBackPath(e.from, e.to);
            // Compute label position: midpoint of the left-margin arc
            const a = effectiveLayout[e.from];
            const b = effectiveLayout[e.to];
            const labelX = a && b ? Math.min(a.x, b.x) - 30 : 0;
            const labelY = a && b ? (a.y + a.h / 2 + b.y + b.h / 2) / 2 : 0;
            return (
              <g key={key} data-edge={key}>
                <path
                  d={d}
                  fill="none"
                  stroke="var(--accent-green, #3fb950)"
                  strokeWidth="1.4"
                  strokeOpacity="0.7"
                  strokeDasharray="5 3"
                  markerEnd="url(#pipe-arrow-right)"
                />
                <text
                  x={labelX}
                  y={labelY}
                  textAnchor="middle"
                  fontSize="9"
                  fill="var(--accent-green, #3fb950)"
                  opacity="0.8"
                  transform={`rotate(-90, ${labelX}, ${labelY})`}
                >
                  re-query (cap 1)
                </text>
              </g>
            );
          }

          return (
            <path
              key={key}
              d={edgePath(e.from, e.to)}
              fill="none"
              stroke="var(--text-tertiary, #888)"
              strokeWidth="1.4"
              strokeOpacity="0.55"
              strokeDasharray={isDashed ? "5 3" : undefined}
              markerEnd="url(#pipe-arrow)"
            />
          );
        })}
      </svg>

      {effectiveNodes.map((n) => {
        const box = effectiveLayout[n.id];
        if (!box) return null;

        // ── diversity node ───────────────────────────────────────────────
        if (n.id === "diversity") {
          return (
            <div
              key={n.id}
              className="pipe2__node pipe2__node--data"
              style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h }}
              data-node={n.id}
            >
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
                <span className="pipe2__badge" title="Click to set author diversity">set</span>
              </div>
              <NodeChoiceDropdown
                value={diversityAuthors}
                options={DIVERSITY_OPTIONS}
                onSelect={onDiversityChange}
                ariaLabel="Author diversity"
              />
            </div>
          );
        }

        // ── drafting workflow node ────────────────────────────────────────
        if (n.id === "drafting") {
          return (
            <div
              key={n.id}
              className="pipe2__node pipe2__node--data"
              style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h }}
              data-node={n.id}
            >
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
                <span className="pipe2__badge" title="Click to set drafting workflow">set</span>
              </div>
              <NodeChoiceDropdown
                value={tutorWorkflow}
                options={WORKFLOW_OPTIONS}
                onSelect={(v) => onWorkflowChange(v as string)}
                ariaLabel="Drafting workflow"
              />
            </div>
          );
        }

        // ── plan node ────────────────────────────────────────────────────
        if (n.id === "plan") {
          const activeId = stageModels["plan"] ?? n.defaultModel;
          return (
            <div
              key={n.id}
              className="pipe2__node pipe2__node--llm"
              style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h }}
              data-node={n.id}
            >
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
                <span className="pipe2__node-sublabel" title={n.desc}>skipped when simple (perspectives ≤ 1)</span>
                <span className="pipe2__badge" title="Click the model to swap">swap</span>
              </div>
              <NodeModelDropdown
                value={activeId}
                providers={providers}
                onChange={(id) => onStageModelChange("plan", id)}
                leadingOptions={[{ label: "Off (single-draft)", value: "off" }]}
              />
            </div>
          );
        }

        // ── orchestrator node (llm, owns the `draft` stage model key) ────
        if (n.id === "orchestrator") {
          let activeId: string = n.defaultModel === "__active__" ? pickerModel : n.defaultModel;
          if (stageModels["draft"]) activeId = stageModels["draft"]!;
          return (
            <div
              key={n.id}
              className="pipe2__node pipe2__node--llm"
              style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h }}
              data-node={n.id}
            >
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
                <span className="pipe2__node-sublabel">decides subtasks</span>
                <span className="pipe2__badge" title="Click the model to swap">swap</span>
              </div>
              <NodeModelDropdown
                value={activeId}
                providers={providers}
                onChange={(id) => onStageModelChange("draft", id)}
              />
            </div>
          );
        }

        // ── worker nodes (static, no dropdown) ──────────────────────────
        if (n.id === "worker1" || n.id === "worker2" || n.id === "worker3") {
          return (
            <div
              key={n.id}
              className="pipe2__node pipe2__node--llm"
              style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h, fontSize: "0.72em" }}
              data-node={n.id}
            >
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
              </div>
            </div>
          );
        }

        // ── synthesizer node (static label, no separate model control) ──
        if (n.id === "synthesizer") {
          return (
            <div
              key={n.id}
              className="pipe2__node pipe2__node--llm"
              style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h }}
              data-node={n.id}
            >
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
                <span className="pipe2__node-sublabel">integrate &amp; compare</span>
              </div>
            </div>
          );
        }

        // ── all other nodes ───────────────────────────────────────────────
        const overridable = n.stage !== null && !n.locked;
        let activeId = n.defaultModel;
        if (n.defaultModel === "__active__") activeId = pickerModel;
        if (overridable && n.stage && stageModels[n.stage]) {
          activeId = stageModels[n.stage]!;
        }

        return (
          <div
            key={n.id}
            className={
              "pipe2__node" +
              (n.locked ? " pipe2__node--locked" : "") +
              ` pipe2__node--${n.kind}`
            }
            style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h }}
            data-node={n.id}
          >
            <div className="pipe2__node-hd">
              <span className="pipe2__node-label">{n.label}</span>
              {n.locked ? (
                <span className="pipe2__lock" title="Fixed model — not swappable">🔒</span>
              ) : (
                <span className="pipe2__badge" title="Click the model to swap">swap</span>
              )}
            </div>
            {n.kind !== "io" && (
              overridable && n.stage ? (
                <NodeModelDropdown
                  value={activeId}
                  providers={providers}
                  onChange={(id) => onStageModelChange(n.stage as StageKey, id)}
                />
              ) : (
                <span className="pipe2__model-fixed">{modelName(providers, activeId) || activeId}</span>
              )
            )}
          </div>
        );
      })}
    </div>
  );
}
