import { useLayoutEffect, useRef, useState } from "react";
import type { ModelProvider } from "../types";
import { TUTOR_PIPELINE, type StageKey } from "../data/tutorPipeline";
import NodeModelDropdown from "./NodeModelDropdown";
import NodeChoiceDropdown, { type ChoiceOption, type ChoiceValue } from "./NodeChoiceDropdown";
import type { PipelineNode } from "../data/tutorPipeline";
import { phaseOf, PHASE_META } from "../data/pipelinePhases";

const DIVERSITY_OPTIONS: ChoiceOption[] = [
  { label: "Off",        value: 0 },
  { label: "Auto",       value: "auto" },
  { label: "2 authors",  value: 2 },
  { label: "3 authors",  value: 3 },
  { label: "4 authors",  value: 4 },
  { label: "5 authors",  value: 5 },
  { label: "6 authors",  value: 6 },
];

interface PipelineDiagramProps {
  pickerModel: string;
  stageModels: Partial<Record<StageKey, string>>;
  providers: ModelProvider[];
  onStageModelChange(stage: StageKey, modelId: string): void;
  diversityAuthors: ChoiceValue;
  onDiversityChange(n: ChoiceValue): void;
}

// Hand-laid layout (px) in a 520×computed coordinate space. Single vertical column:
// Question → Query planner → Hybrid retrieval ×N → Density select + rerank →
// Author diversity → Coverage check → Figure judge → Planner →
// Narrative draft → Vision explain → Answer
//
// Coverage check also has a loop-back edge to Hybrid retrieval (left-side arc).
const W = 560;
interface Box { x: number; y: number; w: number; h: number; }

// Vertical gap between rows.
const GAP = 18;
// Centred nodes geometry. Wide cards fill the modal width so descriptions +
// model names wrap on fewer lines (less vertical sprawl).
const CX = 80;    // left edge of centred nodes
const CW = 400;   // width of centred nodes
// io nodes are a touch narrower + centred in the 560 canvas.
const IO_X = 100;
const IO_W = 360;
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
  { id: "wiki",           h: 112 },
  { id: "def_recovery",   h: 112 },
  { id: "image_judge",    h: 104 },
  { id: "plan",           h: 132 },
  { id: "draft",          h: 104 },
  { id: "vision_explain", h: 112 },
  { id: "output",         h: 46,  io: true },
];

// Default heights used when measured offsetHeight === 0 (jsdom / SSR).
const DEFAULT_H: Record<string, number> = {
  ...Object.fromEntries(ROW_DEF.map((r) => [r.id, r.h])),
};

// ── Layout builder (parametrised by a height getter) ──────────────────────────
function buildLayout(h: (id: string) => number): { layout: Record<string, Box>; height: number } {
  const layout: Record<string, Box> = {};
  let y = TOP;
  for (const r of ROW_DEF) {
    const hh = h(r.id);
    layout[r.id] = r.io ? { x: IO_X, y, w: IO_W, h: hh } : { x: CX, y, w: CW, h: hh };
    y += hh + GAP;
  }
  return { layout, height: y + 8 };
}

// IDs for loop-back edges (go upward; rendered as left-side arcs).
const LOOP_EDGES = new Set(["coverage→retrieval"]);

// ──────────────────────────────────────────────────────────────────────────────

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
}: PipelineDiagramProps) {
  // ── Measurement state ──────────────────────────────────────────────────────
  const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [measured, setMeasured] = useState<Record<string, number>>({});
  const h = (id: string) => measured[id] || DEFAULT_H[id] || 100;

  // ── Build layout from measured (or default) heights ────────────────────────
  const built = buildLayout(h);
  const effectiveLayout = built.layout;
  const canvasH = built.height;

  const effectiveNodes: PipelineNode[] = TUTOR_PIPELINE.nodes;
  const effectiveEdges = TUTOR_PIPELINE.edges;

  // ── Measure node heights after render ──────────────────────────────────────
  useLayoutEffect(() => {
    const next: Record<string, number> = {};
    for (const id of Object.keys(nodeRefs.current)) {
      const el = nodeRefs.current[id];
      if (el && el.offsetHeight > 0) next[id] = el.offsetHeight;
    }
    const keys = new Set([...Object.keys(next), ...Object.keys(measured)]);
    let changed = false;
    for (const k of keys) if (next[k] !== measured[k]) { changed = true; break; }
    if (changed) setMeasured(next);
  });

  // ── Edge path helpers ──────────────────────────────────────────────────────
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

  // ── Render ──────────────────────────────────────────────────────────────────
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
              markerEnd="url(#pipe-arrow)"
            />
          );
        })}
      </svg>

      {effectiveNodes.map((n) => {
        const box = effectiveLayout[n.id];
        if (!box) return null;

        // ── diversity node ─────────────────────────────────────────────────
        if (n.id === "diversity") {
          return (
            <div
              key={n.id}
              ref={(el) => { nodeRefs.current[n.id] = el; }}
              className="pipe2__node pipe2__node--data"
              style={{ position: "absolute", left: box.x, top: box.y, width: box.w }}
              data-node={n.id}
              data-phase={phaseOf(n.id)}
            >
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
                <span className="pipe2__phase-chip" data-phase={phaseOf(n.id)}>
                  {PHASE_META[phaseOf(n.id)].label}
                </span>
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

        // ── plan node ──────────────────────────────────────────────────────
        if (n.id === "plan") {
          const activeId = stageModels["plan"] ?? n.defaultModel;
          return (
            <div
              key={n.id}
              ref={(el) => { nodeRefs.current[n.id] = el; }}
              className="pipe2__node pipe2__node--llm"
              style={{ position: "absolute", left: box.x, top: box.y, width: box.w }}
              data-node={n.id}
              data-phase={phaseOf(n.id)}
            >
              <div className="pipe2__node-hd">
                <span className="pipe2__node-label">{n.label}</span>
                <span className="pipe2__phase-chip" data-phase={phaseOf(n.id)}>
                  {PHASE_META[phaseOf(n.id)].label}
                </span>
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

        // ── all other nodes ────────────────────────────────────────────────
        const overridable = n.stage !== null && !n.locked;
        let activeId = n.defaultModel;
        if (n.defaultModel === "__active__") activeId = pickerModel;
        if (overridable && n.stage && stageModels[n.stage]) {
          activeId = stageModels[n.stage]!;
        }

        return (
          <div
            key={n.id}
            ref={(el) => { nodeRefs.current[n.id] = el; }}
            className={
              "pipe2__node" +
              (n.locked ? " pipe2__node--locked" : "") +
              ` pipe2__node--${n.kind}`
            }
            style={{ position: "absolute", left: box.x, top: box.y, width: box.w }}
            data-node={n.id}
            data-phase={phaseOf(n.id)}
          >
            <div className="pipe2__node-hd">
              <span className="pipe2__node-label">{n.label}</span>
              {n.kind !== "io" && (
                <span className="pipe2__phase-chip" data-phase={phaseOf(n.id)}>
                  {PHASE_META[phaseOf(n.id)].label}
                </span>
              )}
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
