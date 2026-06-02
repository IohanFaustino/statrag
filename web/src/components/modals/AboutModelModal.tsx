import { useEffect, useState } from "react";
import FocusModal from "./FocusModal";
import PipelineDiagram from "../PipelineDiagram";
import { TUTOR_MODE } from "../../data/tutorMode";
import type { StageKey } from "../../data/tutorPipeline";
import type { ModelProvider } from "../../types";

export interface PipelineConfig {
  stageModels: Partial<Record<StageKey, string>>;
  diversityAuthors: number | "auto";
  tutorWorkflow: string;
}

interface AboutModelModalProps {
  open: boolean;
  modelId: string | null;
  providers: ModelProvider[];
  pickerModel: string;
  recommendedModel: string;
  // Currently-applied config (the modal seeds its editable draft from this).
  stageModels: Partial<Record<StageKey, string>>;
  diversityAuthors: number | "auto";
  tutorWorkflow: string;
  // Commit the draft. Called only when the user presses Apply.
  onApply(config: PipelineConfig): void;
  onClose(): void;
}

export default function AboutModelModal({
  open,
  modelId,
  providers,
  pickerModel,
  recommendedModel,
  stageModels,
  diversityAuthors,
  tutorWorkflow,
  onApply,
  onClose,
}: AboutModelModalProps) {
  // Draft state — edits are staged here and only committed on Apply.
  const [draftStageModels, setDraftStageModels] =
    useState<Partial<Record<StageKey, string>>>(stageModels);
  const [draftDiversity, setDraftDiversity] = useState<number | "auto">(diversityAuthors);
  const [draftWorkflow, setDraftWorkflow] = useState<string>(tutorWorkflow);

  // Re-seed the draft from the applied config each time the modal opens.
  useEffect(() => {
    if (open) {
      setDraftStageModels(stageModels);
      setDraftDiversity(diversityAuthors);
      setDraftWorkflow(tutorWorkflow);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open || !modelId) return null;

  const setDefaults = () =>
    setDraftStageModels((prev) => ({
      ...prev,
      expansion: recommendedModel,
      image_judge: recommendedModel,
      plan: recommendedModel,
      draft: recommendedModel,
      vision_explain: recommendedModel,
    }));

  const dirty =
    JSON.stringify(draftStageModels) !== JSON.stringify(stageModels) ||
    draftDiversity !== diversityAuthors ||
    draftWorkflow !== tutorWorkflow;

  const apply = () => {
    onApply({
      stageModels: draftStageModels,
      diversityAuthors: draftDiversity,
      tutorWorkflow: draftWorkflow,
    });
    onClose();
  };

  return (
    <FocusModal
      open={open}
      onClose={onClose}
      size="md"
      panelClassName="fm__panel--about"
      labelledBy="about-model-title"
    >
      <div className="about-model">
        <header className="about-model__hd">
          <div>
            <h2 id="about-model-title" className="about-model__title">{TUTOR_MODE.title}</h2>
            <p className="about-model__blurb">{TUTOR_MODE.blurb}</p>
          </div>
          <button
            type="button"
            className="about-model__close"
            aria-label="Close"
            onClick={onClose}
          >
            ✕
          </button>
        </header>

        <div className="about-model__body">
        <p className="about-model__desc">{TUTOR_MODE.description}</p>

        <section className="about-model__section">
          <h3 className="about-model__sub">Features</h3>
          <ul className="about-model__caps">
            {TUTOR_MODE.features.map((f) => (
              <li key={f.label} className="about-model__cap">
                <strong>{f.label}:</strong> {f.detail}
              </li>
            ))}
          </ul>
        </section>

        <section className="about-model__section">
          <h3 className="about-model__sub">Pipeline — input → output</h3>
        </section>

        <PipelineDiagram
          pickerModel={pickerModel}
          stageModels={draftStageModels}
          providers={providers}
          onStageModelChange={(stage, id) =>
            setDraftStageModels((prev) => ({ ...prev, [stage]: id }))
          }
          diversityAuthors={draftDiversity}
          onDiversityChange={(v) => setDraftDiversity(v as number | "auto")}
          tutorWorkflow={draftWorkflow}
          onWorkflowChange={(v) => setDraftWorkflow(String(v))}
        />
        </div>

        <footer className="about-model__footer">
          <span className="about-model__footer-hint">
            {dirty ? "Unsaved pipeline changes" : "No changes"}
          </span>
          <div className="about-model__footer-actions">
            <button type="button" className="about-model__btn about-model__btn--ghost" onClick={setDefaults}>Default</button>
            <button type="button" className="about-model__btn about-model__btn--ghost" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="about-model__btn about-model__btn--apply"
              onClick={apply}
              disabled={!dirty}
            >
              Apply
            </button>
          </div>
        </footer>
      </div>
    </FocusModal>
  );
}
