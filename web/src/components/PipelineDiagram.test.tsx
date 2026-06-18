import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { stageDefaultModels } from "../data/recommended";
import { TUTOR_PIPELINE } from "../data/tutorPipeline";
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
      />,
    );
    expect(html).toContain("pipe2__node--locked");
    expect(html).toContain("pipe2__model-fixed");
  });

  it("renders the Planner node between Figure judge and Narrative draft (label updated, 'Synthesis plan' gone)", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
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
      />,
    );
    expect(html).toContain("Coverage check");
    expect(html).toContain('data-node="coverage"');
    // locked node — shows lock icon and fixed model text, no dropdown toggle
    expect(html).toContain("pipe2__node--locked");
    expect(html).toContain("facet re-query");
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
      />,
    );
    // The loop-back group has data-edge="coverage-retrieval"
    expect(html).toContain('data-edge="coverage-retrieval"');
    // Label text is present
    expect(html).toContain("re-query (cap 1)");
  });

  it("Query planner, Coverage check, and Hybrid retrieval ×N are all present", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
      />,
    );
    expect(html).toContain("Query planner");
    expect(html).toContain("Coverage check");
    expect(html).toContain("Hybrid retrieval ×N");
  });

  it("Critique node is NOT rendered", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
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
      />,
    );
    expect(html).toContain("Off (single-draft)");
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
      />,
    );
    expect(html).toContain("5 authors");
  });

  it("renders the definition recovery node between Wikipedia augment and Figure judge", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
      />,
    );
    expect(html).toContain("Definition recovery");
    expect(html).toContain('data-node="def_recovery"');
  });

  it("definition recovery node is locked (no model dropdown)", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
      />,
    );
    // Locked nodes show the lock icon class, not the dropdown toggle
    expect(html).toContain('data-node="def_recovery"');
    // The def_recovery node should be a locked data node (no swap dropdown)
    const node = TUTOR_PIPELINE.nodes.find((n) => n.id === "def_recovery");
    expect(node).toBeDefined();
    expect(node!.locked).toBe(true);
  });

  it("renders the Finalize + verify node between draft and vision_explain", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
      />,
    );
    expect(html).toContain("Finalize + verify");
    expect(html).toContain('data-node="finalize"');
    // finalize is a generation-phase LLM node with a model dropdown
    expect(html).toContain('data-phase="generation"');
  });

  it("finalize node is swappable (not locked) with default full model", () => {
    const node = TUTOR_PIPELINE.nodes.find((n) => n.id === "finalize");
    expect(node).toBeDefined();
    expect(node!.locked).toBe(false);
    expect(node!.stage).toBe("finalize");
    expect(node!.defaultModel).toBe("gpt-5.4-2026-03-05");
  });

  it("pipeline edges wire draft → finalize → vision_explain", () => {
    const edgeFromDraft = TUTOR_PIPELINE.edges.find((e) => e.from === "draft");
    expect(edgeFromDraft).toBeDefined();
    expect(edgeFromDraft!.to).toBe("finalize");
    const edgeFromFinalize = TUTOR_PIPELINE.edges.find((e) => e.from === "finalize");
    expect(edgeFromFinalize).toBeDefined();
    expect(edgeFromFinalize!.to).toBe("vision_explain");
  });
});

describe("narrative-only pipeline (Task 6 — tutorWorkflow removed)", () => {
  it("renders a single narrative draft node and no workflow selector", () => {
    const html = renderToStaticMarkup(
      <PipelineDiagram
        pickerModel="gpt-4o"
        stageModels={{}}
        providers={PROVIDERS}
        onStageModelChange={() => {}}
        diversityAuthors={3}
        onDiversityChange={() => {}}
      />,
    );
    // No orchestrator / organize / workflow-variant nodes
    expect(html).not.toContain('data-node="orchestrator"');
    expect(html).not.toContain('data-node="synthesizer"');
    expect(html).not.toContain("Organize");
    // Single narrative draft node must exist
    expect(html).toContain('data-node="draft"');
    expect(html).toContain("Narrative draft");
    // No workflow dropdown (NodeChoiceDropdown) for drafting node
    expect(html).not.toContain('aria-label="Drafting workflow"');
  });
});

it("tags nodes with their phase", () => {
  const html = renderToStaticMarkup(
    <PipelineDiagram
      pickerModel="gpt-4o" stageModels={{}} providers={PROVIDERS}
      onStageModelChange={() => {}} diversityAuthors={3} onDiversityChange={() => {}}
    />,
  );
  expect(html).toContain('data-phase="planning"');
  expect(html).toContain('data-phase="retrieval"');
  expect(html).toContain('data-phase="vision"');
  expect(html).toContain('data-phase="generation"');
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

describe("plan node tooltip regression (I-1)", () => {
  it("plan node desc does not mention orchestrator or worker language", () => {
    const planNode = TUTOR_PIPELINE.nodes.find((n) => n.id === "plan");
    expect(planNode).toBeDefined();
    expect(planNode!.desc).not.toMatch(/orchestrator|worker|per-worker/i);
  });
});

describe("stageDefaultModels (Default button reset map)", () => {
  it("restores true per-stage defaults: nano for non-draft text stages (except finalize=full), gpt-4o-mini vision, recommended draft", () => {
    const defaults = stageDefaultModels("gpt-5.4-nano-2026-03-17");
    expect(defaults).toEqual({
      expansion: "gpt-5.4-nano-2026-03-17",
      image_judge: "gpt-5.4-nano-2026-03-17",
      plan: "gpt-5.4-nano-2026-03-17",
      draft: "gpt-5.4-nano-2026-03-17",
      finalize: "gpt-5.4-2026-03-05",
      vision_explain: "gpt-4o-mini",
    });
    // regression guard: the non-draft stages must NOT all fall back to the old recommended (qwen-plus)
    expect(defaults.plan).not.toBe("qwen-plus");
    expect(defaults.vision_explain).not.toBe("qwen-plus");
  });

  it("draft follows the supplied recommended/draft model so a custom draft pick is honored", () => {
    expect(stageDefaultModels("gpt-5.4").draft).toBe("gpt-5.4");
    // non-draft stages stay on their fixed defaults regardless of the draft pick
    expect(stageDefaultModels("gpt-5.4").plan).toBe("gpt-5.4-nano-2026-03-17");
  });
});
