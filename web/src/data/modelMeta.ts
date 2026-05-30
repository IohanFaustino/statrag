// Static, author-maintained metadata for the "About this model" modal.
// Keyed by the model ids in the backend registry (src/services/chat/llm/router.py).
// Keep ids in sync with that registry.

export interface ModelCapability {
  label: string;
  detail: string;
}

export interface ModelMeta {
  id: string;
  blurb: string; // one-line summary
  description: string; // 2-4 sentence prose
  capabilities: ModelCapability[];
  // True when this model can drive the tutor's structured draft directly.
  // OpenAI models use the native structured-streaming path; deepseek runs a
  // best-effort JSON path (may be slower / less reliable for synthesis).
  tutorDraft: "native" | "best-effort";
}

const FALLBACK: ModelMeta = {
  id: "unknown",
  blurb: "Model details unavailable",
  description: "No static metadata is registered for this model yet.",
  capabilities: [],
  tutorDraft: "best-effort",
};

export const MODEL_META: Record<string, ModelMeta> = {
  "gpt-4o": {
    id: "gpt-4o",
    blurb: "Multimodal flagship",
    description:
      "OpenAI's flagship multimodal model. Strong general reasoning and instruction-following with native vision, suited to high-quality tutor synthesis where answer depth matters more than cost.",
    capabilities: [
      { label: "Context", detail: "128k tokens" },
      { label: "Vision", detail: "Native image understanding" },
      { label: "Structured output", detail: "Native JSON-schema streaming" },
      { label: "Best for", detail: "Draft / synthesis stage" },
    ],
    tutorDraft: "native",
  },
  "gpt-4o-mini": {
    id: "gpt-4o-mini",
    blurb: "Cheap + fast",
    description:
      "A smaller, cheaper sibling of GPT-4o. Fast and inexpensive while keeping solid instruction-following; a good default for the figure-judge and expansion stages, and an economical draft model.",
    capabilities: [
      { label: "Context", detail: "128k tokens" },
      { label: "Vision", detail: "Native (used for figure judging)" },
      { label: "Cost", detail: "Low" },
      { label: "Best for", detail: "Expansion / image-judge / cheap draft" },
    ],
    tutorDraft: "native",
  },
  "gpt-5.4-nano-2026-03-17": {
    id: "gpt-5.4-nano-2026-03-17",
    blurb: "Project default — cheap nano",
    description:
      "The project default. A very cheap, fast nano model used for the pipeline's auxiliary LLM steps (concept extraction, caption judging, critique). Adequate for short structured tasks rather than long synthesis.",
    capabilities: [
      { label: "Context", detail: "200k tokens" },
      { label: "Cost", detail: "Very low" },
      { label: "Speed", detail: "Fast" },
      { label: "Best for", detail: "Expansion / critique / image-judge" },
    ],
    tutorDraft: "native",
  },
  "gpt-5.4-2026-03-05": {
    id: "gpt-5.4-2026-03-05",
    blurb: "Full reasoning",
    description:
      "The full GPT-5.4 reasoning model. Highest answer quality and deepest reasoning at the highest cost; best reserved for the draft/synthesis stage on hard questions.",
    capabilities: [
      { label: "Context", detail: "400k tokens" },
      { label: "Reasoning", detail: "Deep" },
      { label: "Cost", detail: "Highest" },
      { label: "Best for", detail: "Draft / synthesis stage" },
    ],
    tutorDraft: "native",
  },
  "deepseek-chat": {
    id: "deepseek-chat",
    blurb: "General purpose",
    description:
      "DeepSeek's general-purpose chat model. Capable and inexpensive. For the tutor draft it runs through a best-effort JSON path rather than native schema streaming, so synthesis may be slower or less strictly structured.",
    capabilities: [
      { label: "Context", detail: "128k tokens" },
      { label: "Cost", detail: "Low" },
      { label: "Tutor draft", detail: "Best-effort JSON path" },
    ],
    tutorDraft: "best-effort",
  },
  "deepseek-reasoner": {
    id: "deepseek-reasoner",
    blurb: "Chain-of-thought",
    description:
      "DeepSeek's reasoning model with explicit chain-of-thought. Strong on multi-step problems but slower. Tutor draft uses the best-effort JSON path.",
    capabilities: [
      { label: "Context", detail: "128k tokens" },
      { label: "Reasoning", detail: "Chain-of-thought" },
      { label: "Speed", detail: "Slow" },
      { label: "Tutor draft", detail: "Best-effort JSON path" },
    ],
    tutorDraft: "best-effort",
  },
  "deepseek-v4-pro": {
    id: "deepseek-v4-pro",
    blurb: "Latest pro tier",
    description:
      "DeepSeek's latest pro-tier model. Balanced speed and quality at moderate cost. Tutor draft uses the best-effort JSON path.",
    capabilities: [
      { label: "Context", detail: "128k tokens" },
      { label: "Cost", detail: "Moderate" },
      { label: "Tutor draft", detail: "Best-effort JSON path" },
    ],
    tutorDraft: "best-effort",
  },
};

export function getModelMeta(id: string): ModelMeta {
  return MODEL_META[id] ?? { ...FALLBACK, id };
}
