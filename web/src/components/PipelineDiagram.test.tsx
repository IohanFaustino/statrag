import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { stageDefaultModels } from "../data/recommended";
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
    // The plan node's skip condition is conveyed via its in-box description
    // (the old inline sublabel was folded into the desc for layout parity).
    expect(html).toContain("Skipped when the planner rates the question simple");
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

  it("renders the deep-synthesis workflow option", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="orchestrator-deep"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain("Deep synthesis (slower ~45s)");
    // orchestrator-deep uses the orchestrator layout: cluster nodes present
    expect(html).toContain('data-node="orchestrator"');
    expect(html).toContain('data-node="synthesizer"');
    expect(html).toContain("Worker · N");
    // synthesizer node reflects the deepagents+skill->schema-fill path
    expect(html).toContain("deepagents + skill → schema-fill");
    expect(html).not.toContain("integrate &amp; compare");
    // single draft box must NOT be rendered in this mode
    expect(html).not.toContain("Draft / synthesis");
    expect(html).not.toContain('data-node="draft"');
  });

  it("orchestrator (non-deep) synthesizer keeps the integrate & compare sublabel", () => {
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
    expect(html).toContain("integrate &amp; compare");
    expect(html).not.toContain("deepagents + skill → schema-fill");
  });

  it("orchestrator-deep: synthesizer renders editable dropdown defaulting to nano id when stageModels.synth is unset", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="orchestrator-deep"
        onWorkflowChange={() => {}}
      />,
    );
    // Synthesizer node must have an editable dropdown toggle in deep mode
    expect(html).toContain('data-node="synthesizer"');
    expect(html).toContain("node-dd__toggle");
    // nano id not in PROVIDERS fixture → rendered as raw id in toggle name span
    expect(html).toContain("gpt-5.4-nano-2026-03-17");
  });

  it("orchestrator-deep: synthesizer shows override model name when stageModels.synth is set", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{ synth: "gpt-4o-mini" }}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="orchestrator-deep"
        onWorkflowChange={() => {}}
      />,
    );
    expect(html).toContain('data-node="synthesizer"');
    // gpt-4o-mini is in PROVIDERS fixture → its display name should appear in the toggle
    expect(html).toContain("GPT-4o mini");
    // The synthesizer dropdown aria-label reflects the override, not nano
    expect(html).toContain('aria-label="Model: GPT-4o mini. Click to change."');
  });

  it("plain orchestrator: synthesizer renders READ-ONLY draft model badge, NOT an editable synth dropdown", () => {
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
    // Synthesizer node must be present
    expect(html).toContain('data-node="synthesizer"');
    // Extract the synthesizer node's segment to scope assertions
    const synthStart = html.indexOf('data-node="synthesizer"');
    const synthEnd = html.indexOf('data-node=', synthStart + 1);
    const synthSegment = synthEnd === -1 ? html.slice(synthStart) : html.slice(synthStart, synthEnd);
    // Read-only badge class must be present in the synthesizer node
    expect(synthSegment).toContain("pipe2__model-fixed");
    // The badge shows the draft model (pickerModel "gpt-4o" → "GPT-4o")
    expect(synthSegment).toContain("GPT-4o");
    // NO editable dropdown toggle inside the synthesizer node
    expect(synthSegment).not.toContain("node-dd__toggle");
  });

  it("plain orchestrator: synthesizer read-only badge tracks stageModels.draft when set", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{ draft: "deepseek-chat" }}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="orchestrator"
        onWorkflowChange={() => {}}
      />,
    );
    const synthStart = html.indexOf('data-node="synthesizer"');
    const synthEnd = html.indexOf('data-node=', synthStart + 1);
    const synthSegment = synthEnd === -1 ? html.slice(synthStart) : html.slice(synthStart, synthEnd);
    // Badge shows the draft override model name, not the picker
    expect(synthSegment).toContain("DeepSeek Chat");
    // stageModels.synth is NOT set but we're in plain orchestrator — no dropdown
    expect(synthSegment).not.toContain("node-dd__toggle");
  });

  it("plain orchestrator: setting stageModels.synth does NOT change the synthesizer badge (synth ignored in this mode)", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{ synth: "gpt-4o-mini" }}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
        tutorWorkflow="orchestrator"
        onWorkflowChange={() => {}}
      />,
    );
    const synthStart = html.indexOf('data-node="synthesizer"');
    const synthEnd = html.indexOf('data-node=', synthStart + 1);
    const synthSegment = synthEnd === -1 ? html.slice(synthStart) : html.slice(synthStart, synthEnd);
    // Should show the draft model (pickerModel "gpt-4o" → "GPT-4o"), NOT "GPT-4o mini"
    expect(synthSegment).toContain("GPT-4o");
    expect(synthSegment).toContain("pipe2__model-fixed");
    // synth override must NOT drive a dropdown in plain orchestrator
    expect(synthSegment).not.toContain("node-dd__toggle");
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
        recommendedModel="qwen-plus"
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
        recommendedModel="qwen-plus"
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

describe("stageDefaultModels (Default button reset map)", () => {
  it("restores true per-stage defaults: nano for non-draft text stages, gpt-4o-mini vision, recommended draft — NOT the recommended model everywhere", () => {
    const defaults = stageDefaultModels("gpt-5.4-nano-2026-03-17");
    expect(defaults).toEqual({
      expansion: "gpt-5.4-nano-2026-03-17",
      image_judge: "gpt-5.4-nano-2026-03-17",
      plan: "gpt-5.4-nano-2026-03-17",
      synth: "gpt-5.4-nano-2026-03-17",
      draft: "gpt-5.4-nano-2026-03-17",
      vision_explain: "gpt-4o-mini",
    });
    // regression guard: the non-draft stages must NOT all fall back to the old recommended (qwen-plus)
    expect(defaults.plan).not.toBe("qwen-plus");
    expect(defaults.synth).not.toBe("qwen-plus");
    expect(defaults.vision_explain).not.toBe("qwen-plus");
  });

  it("draft follows the supplied recommended/draft model so a custom draft pick is honored", () => {
    expect(stageDefaultModels("gpt-5.4").draft).toBe("gpt-5.4");
    // non-draft stages stay on their fixed defaults regardless of the draft pick
    expect(stageDefaultModels("gpt-5.4").plan).toBe("gpt-5.4-nano-2026-03-17");
  });
});
