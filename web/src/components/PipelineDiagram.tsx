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
  { label: "Deep synthesis (slower ~45s)", value: "orchestrator-deep" },
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

// Hand-laid layout (px) in a 520×computed coordinate space. Single vertical column:
// Question → Query planner → Hybrid retrieval ×N → Density select + rerank →
// Author diversity → Coverage check → Figure judge → Planner →
// Drafting workflow → Draft / synthesis → Vision explain → Answer
//
// Coverage check also has a loop-back edge to Hybrid retrieval (left-side arc).
const W = 520;
interface Box { x: number; y: number; w: number; h: number; }

// Vertical gap between rows.
const GAP = 18;
// Centred nodes geometry.
const CX = 144;   // left edge of centred nodes
const CW = 232;   // width of centred nodes
// io nodes are a touch narrower + centred in the 520 canvas.
const IO_X = 160;
const IO_W = 200;
const TOP = 8;    // top padding

// Ordered rows with per-node heights (sized to fit label + clamped desc +
// the model control). Growing a height auto-reflows everything below.
const ROW_DEF: ReadonlyArray<{ id: string; h: number; io?: boolean }> = [
  { id: "input",          h: 46,  io: true },
  { id: "expansion",      h: 122 },
  { id: "retrieval",      h: 104 },
  { id: "rerank",         h: 112 },
  { id: "diversity",      h: 116 },
  { id: "coverage",       h: 112 },
  { id: "image_judge",    h: 104 },
  { id: "plan",           h: 132 },
  { id: "drafting",       h: 132 },
  { id: "draft",          h: 104 },
  { id: "vision_explain", h: 112 },
  { id: "output",         h: 46,  io: true },
];

const BASE_LAYOUT: Record<string, Box> = (() => {
  const out: Record<string, Box> = {};
  let y = TOP;
  for (const r of ROW_DEF) {
    out[r.id] = r.io
      ? { x: IO_X, y, w: IO_W, h: r.h }
      : { x: CX,   y, w: CW,   h: r.h };
    y += r.h + GAP;
  }
  return out;
})();

const BASE_H = (() => {
  let y = TOP;
  for (const r of ROW_DEF) y += r.h + GAP;
  return y + 8; // bottom padding
})();

// ── orchestrator cluster geometry ──────────────────────────────────────────
// The `draft` slot starts at y=848. The orchestrator cluster replaces it with:
//   - orchestrator node (same position as draft)
//   - worker row (3 workers side-by-side) below orchestrator
//   - synthesizer below the worker row
// Nodes that follow (vision_explain, output) are shifted down.

const ORCH_Y       = BASE_LAYOUT.draft.y;  // where draft was (848)
const ORCH_H       = 104;  // fits label + desc + model dropdown (matches draft node)
const WORKER_ROW_Y = ORCH_Y + ORCH_H + 18;  // 848
const WORKER_H     = 56;
// Formula recovery sits between the worker row and the synthesizer: the workers'
// briefs are scanned for OCR-dropped defining equations, recovered (vision/text),
// and handed to the synthesizer. Locked (vision + cache), no model dropdown.
const FR_Y         = WORKER_ROW_Y + WORKER_H + 18;
const FR_H         = 88;
const SYNTH_Y      = FR_Y + FR_H + 18;
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
  formula_recovery: { x: BASE_LAYOUT.draft.x, y: FR_Y, w: BASE_LAYOUT.draft.w, h: FR_H },
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
    id: "formula_recovery",
    label: "Formula recovery",
    desc: "Gap-triggered · best-effort. If a concept's defining equation was OCR-dropped to a figure, recover it per gap in parallel: formula_cache → vision reads it off the figure (gpt-4o) → text re-query. Injected into the synth as <recovered_equations> (used verbatim) and cached. No-op on failure.",
    kind: "data",
    stage: null,
    defaultModel: "gpt-4o vision + formula_cache",
    locked: true,
  },
  {
    id: "synthesizer",
    label: "Synthesizer",
    desc: "Integrates & compares per-author drafts into the final answer. In plain orchestrator mode the synthesizer runs on the draft model; switch to deep synthesis (orchestrator-deep) to select a dedicated synthesis model (default nano) that drives the deepagents synthesizer + nano schema-fill.",
    kind: "llm",
    stage: "synth",
    defaultModel: "gpt-5.4-nano-2026-03-17",
    locked: false,
  },
];

// Edges that replace the single `drafting → draft` edge. Workers' briefs flow
// through the formula-recovery stage before the synthesizer integrates them.
const ORC_EDGES: PipelineEdge[] = [
  { from: "drafting",          to: "orchestrator" },
  { from: "orchestrator",      to: "worker1" },
  { from: "orchestrator",      to: "worker2" },
  { from: "orchestrator",      to: "worker3" },
  { from: "worker1",           to: "formula_recovery" },
  { from: "worker2",           to: "formula_recovery" },
  { from: "worker3",           to: "formula_recovery" },
  { from: "formula_recovery",  to: "synthesizer" },
  { from: "synthesizer",       to: "vision_explain" },
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
  const isOrchLayout = tutorWorkflow === "orchestrator" || tutorWorkflow === "orchestrator-deep";

  // ── Derive effective graph ───────────────────────────────────────────────
  let effectiveNodes: PipelineNode[];
  let effectiveEdges: PipelineEdge[];
  let effectiveLayout: Record<string, Box>;
  let canvasH: number;

  if (!isOrchLayout) {
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
              <div className="pipe2__node-desc pipe2__node-desc--clamp" title={n.desc}>{n.desc}</div>
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
              <div className="pipe2__node-desc pipe2__node-desc--clamp" title={n.desc}>{n.desc}</div>
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
                <span className="pipe2__badge" title="Click the model to swap">swap</span>
              </div>
              <div className="pipe2__node-desc pipe2__node-desc--clamp" title={n.desc}>{n.desc}</div>
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
                <span className="pipe2__badge" title="Click the model to swap">swap</span>
              </div>
              <div className="pipe2__node-desc pipe2__node-desc--clamp" title={n.desc}>{n.desc}</div>
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

        // ── synthesizer node ─────────────────────────────────────────────
        // deepSynth (orchestrator-deep): editable synth model dropdown.
        // plain orchestrator: read-only badge showing the draft model (the L0
        // synthesizer actually runs on the draft model in that path).
        if (n.id === "synthesizer") {
          const deepSynth = tutorWorkflow === "orchestrator-deep";
          const synthActive = stageModels["synth"] ?? n.defaultModel;
          const draftActive = stageModels["draft"] ?? pickerModel;
          return (
            <div
              key={n.id}
              className="pipe2__node pipe2__node--llm"
              style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h }}
              data-node={n.id}
            >
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
                <span className="pipe2__node-sublabel">
                  {deepSynth ? "deepagents + skill → schema-fill" : "integrate & compare"}
                </span>
              </div>
              {deepSynth ? (
                <NodeModelDropdown
                  value={synthActive}
                  providers={providers}
                  onChange={(id) => onStageModelChange("synth" as StageKey, id)}
                />
              ) : (
                <span className="pipe2__model-fixed">{modelName(providers, draftActive) || draftActive}</span>
              )}
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
              <div className="pipe2__node-desc pipe2__node-desc--clamp" title={n.desc}>{n.desc}</div>
            )}
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
