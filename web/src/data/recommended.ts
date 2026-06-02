import type { ModelProvider } from "../types";

// The system-recommended model id. Must match the registry entry flagged
// `recommended: true` in src/services/chat/llm/router.py (qwen-plus).
export const RECOMMENDED_MODEL_ID = "qwen-plus";

/** The recommended model id from the live registry (the model flagged
 *  `recommended`), falling back to the static constant. */
export function recommendedModelId(providers: ModelProvider[]): string {
  for (const p of providers) {
    const m = p.models.find((mm) => mm.recommended);
    if (m) return m.id;
  }
  return RECOMMENDED_MODEL_ID;
}
