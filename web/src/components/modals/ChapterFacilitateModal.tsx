import { useEffect, useState } from "react";
import FocusModal from "./FocusModal";
import ChapterPipelineDiagram from "../ChapterPipelineDiagram";
import { FACILITATE_MODE } from "../../data/chapterMode";
import type { ModelProvider } from "../../types";

interface ChapterFacilitateModalProps {
  open: boolean;
  providers: ModelProvider[];
  stageModels: Record<string, string>;
  onApply(cfg: { stageModels: Record<string, string> }): void;
  onClose(): void;
}

// Chapter pipeline stages whose models are user-overridable.
const CHAPTER_STAGES = ["parse", "resolve", "map", "stitch", "ground"] as const;

export default function ChapterFacilitateModal({
  open,
  providers,
  stageModels,
  onApply,
  onClose,
}: ChapterFacilitateModalProps) {
  const [draft, setDraft] = useState<Record<string, string>>(stageModels);

  useEffect(() => {
    if (open) setDraft(stageModels);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const dirty = CHAPTER_STAGES.some((s) => draft[s] !== stageModels[s]);
  const apply = () => {
    onApply({ stageModels: draft });
    onClose();
  };

  return (
    <FocusModal open={open} onClose={onClose} size="md" panelClassName="fm__panel--about" labelledBy="facilitate-modal-title">
      <div className="about-model">
        <header className="about-model__hd">
          <div>
            <h2 id="facilitate-modal-title" className="about-model__title">{FACILITATE_MODE.title}</h2>
            <p className="about-model__blurb">{FACILITATE_MODE.blurb}</p>
          </div>
          <button type="button" className="about-model__close" aria-label="Close" onClick={onClose}>✕</button>
        </header>

        <div className="about-model__body">
          <p className="about-model__desc">{FACILITATE_MODE.description}</p>

          <section className="about-model__section">
            <h3 className="about-model__sub">Features</h3>
            <ul className="about-model__caps">
              {FACILITATE_MODE.features.map((f) => (
                <li key={f.label} className="about-model__cap">
                  <strong>{f.label}:</strong> {f.detail}
                </li>
              ))}
            </ul>
          </section>

          <section className="about-model__section">
            <h3 className="about-model__sub">Pipeline — input → output</h3>
          </section>
          <ChapterPipelineDiagram
            mode="facilitate"
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
