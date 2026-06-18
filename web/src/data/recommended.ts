import type { ModelProvider } from "../types";
import type { StageKey } from "./tutorPipeline";

// The system-recommended model id. Must match the registry entry flagged
// `recommended: true` in src/services/chat/llm/router.py (gpt-5.4-nano-2026-03-17).
export const RECOMMENDED_MODEL_ID = "gpt-5.4-nano-2026-03-17";

// Cheap default for the non-draft text stages. Mirrors the backend
// `settings.openai_model_nano` used by `_resolve_stage_model` for every
// non-draft stage (deep_tutor.py).
export const NANO_MODEL_ID = "gpt-5.4-nano-2026-03-17";
// Full reasoning model. Mirrors backend `settings.openai_model_full`
// used by the finalize stage (deep_tutor.py).
export const FULL_MODEL_ID = "gpt-5.4-2026-03-05";
// Vision-explain default. Mirrors backend `_vision_default_model` (gpt-4o-mini).
export const VISION_DEFAULT_MODEL_ID = "gpt-4o-mini";

/** The true per-stage default model ids, mirroring the backend
 *  `_resolve_stage_model` (deep_tutor.py): non-draft text stages → nano;
 *  vision_explain → gpt-4o-mini; draft → the recommended draft model
 *  (TUTOR_DRAFT_MODEL). The "Default" button restores exactly this map; the
 *  per-stage dropdowns still override any of these freely. */
export function stageDefaultModels(recommendedModel: string): Record<StageKey, string> {
  return {
    expansion: NANO_MODEL_ID,
    image_judge: NANO_MODEL_ID,
    plan: NANO_MODEL_ID,
    draft: recommendedModel,
    finalize: FULL_MODEL_ID,
    vision_explain: VISION_DEFAULT_MODEL_ID,
  };
}

/** The recommended model id from the live registry (the model flagged
 *  `recommended`), falling back to the static constant. */
export function recommendedModelId(providers: ModelProvider[]): string {
  for (const p of providers) {
    const m = p.models.find((mm) => mm.recommended);
    if (m) return m.id;
  }
  return RECOMMENDED_MODEL_ID;
}
