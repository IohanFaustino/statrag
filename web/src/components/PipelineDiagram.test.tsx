import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PipelineDiagram from "./PipelineDiagram";
import AboutModelModal from "./modals/AboutModelModal";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  {
    id: "openai", name: "OpenAI", short: "OAI", color: "#10A37F",
    models: [
      { id: "gpt-4o", name: "GPT-4o", tagline: "flagship", cost: "$$$", speed: "fast", ctx: "128k" },
      { id: "gpt-4o-mini", name: "GPT-4o mini", tagline: "cheap", cost: "$", speed: "fast", ctx: "128k" },
    ],
  },
  {
    id: "deepseek", name: "DeepSeek", short: "DS", color: "#4D6BFE",
    models: [
      { id: "deepseek-chat", name: "DeepSeek Chat", tagline: "gp", cost: "$", speed: "fast", ctx: "128k" },
    ],
  },
];

describe("PipelineDiagram", () => {
  it("renders a swappable custom dropdown for the draft node defaulting to the picker model", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    // swappable nodes use the custom dropdown toggle (not a native select)
    expect(html).toContain("node-dd__toggle");
    expect(html).not.toContain("<select");
    // draft toggle shows the active picker model name
    expect(html).toContain("GPT-4o");
    // nodes now show an in-box description line (parity with qa/chapter modals)
    expect(html).toContain("pipe2__node-desc");
    expect(html).toContain("Interprets the question");
  });

  it("shows the override value once a stage model is set", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{ draft: "deepseek-chat" }}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    // draft toggle now reflects the override model name
    expect(html).toContain("DeepSeek Chat");
  });

  it("renders locked nodes (embedding / vision) as fixed, not selectable", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain("pipe2__node--locked");
    expect(html).toContain("pipe2__model-fixed");
  });

  it("renders the Planner node between Figure judge and Draft (label updated, 'Synthesis plan' gone)", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    // New label
    expect(html).toContain("Planner");
    // Old label must be gone
    expect(html).not.toContain("Synthesis plan");
    // plan node uses the model dropdown (node-dd__toggle present)
    expect(html).toContain("node-dd__toggle");
    // plan node is positioned in the layout
    expect(html).toContain('data-node="plan"');
  });

  it("plan node annotates that it is skipped when planner rates question simple (Phase 3)", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    // Sublabel annotation must be present on the plan node
    expect(html).toContain("skipped when simple");
    expect(html).toContain("perspectives");
  });

  it("expansion node is labelled 'Query planner' and 'Concept extraction' is gone", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain("Query planner");
    expect(html).not.toContain("Concept extraction");
  });

  it("coverage node renders as a locked data node with 'Coverage check' label", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain("Coverage check");
    expect(html).toContain('data-node="coverage"');
    // locked node — shows lock icon and fixed model text, no dropdown toggle
    expect(html).toContain("pipe2__node--locked");
    expect(html).toContain("facet re-query");
  });

  it("coverage node is present in orchestrator mode too", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="orchestrator"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain("Coverage check");
    expect(html).toContain('data-node="coverage"');
  });

  it("renders the coverage→retrieval loop-back edge (path keyed coverage-retrieval)", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    // The loop-back group has data-edge="coverage-retrieval"
    expect(html).toContain('data-edge="coverage-retrieval"');
    // Label text is present
    expect(html).toContain("re-query (cap 1)");
  });

  it("single mode: Query planner, Coverage check, and Hybrid retrieval ×N are all present", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain("Query planner");
    expect(html).toContain("Coverage check");
    expect(html).toContain("Hybrid retrieval ×N");
  });

  it("single mode: Critique node is NOT rendered", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).not.toContain("Critique");
    expect(html).not.toContain('data-node="critique"');
  });

  it("orchestrator mode: Critique node is NOT rendered", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="orchestrator"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).not.toContain("Critique");
    expect(html).not.toContain('data-node="critique"');
  });

  it("shows Off (single-draft) label when plan stage model is set to off", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{ plan: "off" }}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain("Off (single-draft)");
  });

  it("renders the Drafting workflow node and shows correct label for orchestrator workflow", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="orchestrator"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain("Drafting workflow");
    expect(html).toContain('data-node="drafting"');
    expect(html).toContain("Orchestrator (per author)");
  });

  it("orchestrator mode: renders Orchestrator + Synthesizer cluster and NOT the single Draft node", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="orchestrator"
        onWorkflowChange={() => {}}
      />,
    );
    // Cluster nodes present
    expect(html).toContain("Orchestrator");
    expect(html).toContain("Synthesizer");
    expect(html).toContain('data-node="orchestrator"');
    expect(html).toContain('data-node="synthesizer"');
    // Worker nodes present
    expect(html).toContain("Worker · N");
    // Single draft box must NOT be rendered
    expect(html).not.toContain("Draft / synthesis");
    expect(html).not.toContain('data-node="draft"');
  });

  it("single mode: renders Draft / synthesis node and NOT the orchestrator cluster", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    // Single draft box present
    expect(html).toContain("Draft / synthesis");
    expect(html).toContain('data-node="draft"');
    // Orchestrator cluster must NOT be rendered
    expect(html).not.toContain('data-node="orchestrator"');
    expect(html).not.toContain("Synthesizer");
  });

  it("rerank node label contains 'adjacent sections' (Change 1)", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain("adjacent sections");
    expect(html).toContain('data-node="rerank"');
  });

  it("diversity dropdown renders '5 authors' label when diversityAuthors=5 (Change 2)", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={5}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain("5 authors");
  });

  it("diversity dropdown renders '6 authors' label when diversityAuthors=6 (Change 2)", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={6}
        onDiversityChange={() => {}}
        tutorWorkflow="single"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain("6 authors");
  });
});

describe("AboutModelModal", () => {
  it("renders nothing when closed", () => {
    const html = renderToStaticMarkup(
      <AboutModelModal
        open={false}
        modelId={null}
        providers={PROVIDERS}
        pickerModel="gpt-4o"
        stageModels={{}}
        diversityAuthors={3}
        tutorWorkflow="single"
        onApply={() => {}}
        onClose={() => {}}
      />,
    );
    expect(html).toBe("");
  });

  it("renders the tutor-mode title, features and the diagram when open", () => {
    const html = renderToStaticMarkup(
      <AboutModelModal
        open
        modelId="gpt-4o"
        providers={PROVIDERS}
        pickerModel="gpt-4o"
        stageModels={{}}
        diversityAuthors={3}
        tutorWorkflow="single"
        onApply={() => {}}
        onClose={() => {}}
      />,
    );
    expect(html).toContain("Tutor mode");
    expect(html).toContain("Features");
    expect(html).toContain("node-dd__toggle"); // diagram embedded w/ custom dropdown
    expect(html).toContain("Apply"); // Apply button present
  });
});
