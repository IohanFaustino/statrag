import FocusModal from "./FocusModal";
import ExtensionPipelineDiagram from "../ExtensionPipelineDiagram";

const EXTENSION_MODE = {
  title: "Extension mode",
  blurb: "Deep chapter digest with augmented footnotes from the wider corpus",
  description:
    "Extension mode produces a structured chapter digest via a topology-C agentic pipeline. It resolves the target chapter, fetches section structure, dispatches per-section analyst subagents (gap taxonomy: formal-def / formula-deriv / comparative / application), curates a timeline via the polish stage, fills coverage gaps with corpus retrieval and Wikipedia (fit rubric 1–5), then runs a judge loop that verifies completeness, merges orphan footnotes, and enforces footnote density (≥ 2 per non-trivial point) before delivering the final ExtensionDigest.",
  features: [
    { label: "Topology-C pipeline", detail: "Resolve → fetch structure → per-section analysts → polish → augmentor → judge loop. All augmentation lives in footnotes — curated_text is never modified." },
    { label: "Gap taxonomy", detail: "Analyst classifies each gap as: [FORMAL-DEF] undefined concept, [FORMULA-DERIV] missing derivation, [COMPARATIVE] no cross-book context, or [APPLICATION] no worked example." },
    { label: "Fit-rubric augmentation", detail: "Augmentor scores each retrieved source 1–5 for relevance. Score 1–2: discarded. Score 3–5: written as footnote (≥ 40 words). Wikipedia disambiguation fallback on 404." },
    { label: "Judge loop", detail: "Capped re-call loop: parses COVERAGE markers, merges orphan footnotes, verifies all fields are in English, and re-delegates augmentor if any point has 0 footnotes after the first pass." },
  ],
} as const;

interface ExtensionModeModalProps {
  open: boolean;
  onClose(): void;
}

export default function ExtensionModeModal({ open, onClose }: ExtensionModeModalProps) {
  if (!open) return null;

  return (
    <FocusModal open={open} onClose={onClose} size="md" panelClassName="fm__panel--about" labelledBy="extension-modal-title">
      <div className="about-model">
        <header className="about-model__hd">
          <div>
            <h2 id="extension-modal-title" className="about-model__title">{EXTENSION_MODE.title}</h2>
            <p className="about-model__blurb">{EXTENSION_MODE.blurb}</p>
          </div>
          <button type="button" className="about-model__close" aria-label="Close" onClick={onClose}>✕</button>
        </header>

        <div className="about-model__body">
          <p className="about-model__desc">{EXTENSION_MODE.description}</p>

          <section className="about-model__section">
            <h3 className="about-model__sub">Features</h3>
            <ul className="about-model__caps">
              {EXTENSION_MODE.features.map((f) => (
                <li key={f.label} className="about-model__cap">
                  <strong>{f.label}:</strong> {f.detail}
                </li>
              ))}
            </ul>
          </section>

          <section className="about-model__section">
            <h3 className="about-model__sub">Pipeline — input → output</h3>
          </section>
          <ExtensionPipelineDiagram />
        </div>

        <footer className="about-model__footer">
          <div className="about-model__footer-actions">
            <button type="button" className="about-model__btn about-model__btn--ghost" onClick={onClose}>Close</button>
          </div>
        </footer>
      </div>
    </FocusModal>
  );
}
