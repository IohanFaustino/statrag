import { useEffect, useState } from "react";
import FocusModal from "./FocusModal";
import QAPipelineDiagram from "../QAPipelineDiagram";
import type { ModelProvider } from "../../types";

interface QAModeModalProps {
  open: boolean;
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onApply(cfg: { stageModels: Record<string, string> }): void;
  onClose(): void;
}

// Q&A pipeline stages whose models are user-overridable.
const QA_STAGES = ["scope", "generate", "verify"] as const;

export default function QAModeModal({
  open,
  providers,
  stageModels,
  onApply,
  onClose,
}: QAModeModalProps) {
  const [draft, setDraft] = useState<Record<string, string>>(stageModels);

  // Re-seed the draft from the applied config each time the modal opens.
  useEffect(() => {
    if (open) setDraft(stageModels);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const dirty = QA_STAGES.some((s) => draft[s] !== stageModels[s]);
  const apply = () => {
    onApply({ stageModels: draft });
    onClose();
  };

  return (
    <FocusModal open={open} onClose={onClose} size="md" panelClassName="fm__panel--about" labelledBy="qa-modal-title">
      <div className="about-model">
        <header className="about-model__hd">
          <div>
            <h2 id="qa-modal-title" className="about-model__title">Q&amp;A mode</h2>
            <p className="about-model__blurb">Punctual Q&amp;A: scope → retrieve → generate → verify</p>
          </div>
          <button type="button" className="about-model__close" aria-label="Close" onClick={onClose}>✕</button>
        </header>

        <div className="about-model__body">
          <section className="about-model__section">
            <h3 className="about-model__sub">Pipeline — input → output</h3>
          </section>
          <QAPipelineDiagram
            providers={providers}
            stageModels={draft}
            onStageModelChange={(stage, id) => setDraft((prev) => ({ ...prev, [stage]: id }))}
          />
        </div>

        <footer className="about-model__footer">
          <span className="about-model__footer-hint">{dirty ? "Unsaved pipeline changes" : "No changes"}</span>
          <div className="about-model__footer-actions">
            <button type="button" className="about-model__btn about-model__btn--ghost" onClick={onClose}>Cancel</button>
            <button type="button" className="about-model__btn about-model__btn--apply" onClick={apply} disabled={!dirty}>Apply</button>
          </div>
        </footer>
      </div>
    </FocusModal>
  );
}
