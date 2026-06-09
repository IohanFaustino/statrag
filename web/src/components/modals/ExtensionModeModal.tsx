import FocusModal from "./FocusModal";
import ExtensionPipelineDiagram from "../ExtensionPipelineDiagram";

const EXTENSION_MODE = {
  title: "Extension mode",
  blurb: "Deep chapter digest with augmented context",
  description:
    "Extension mode produces a structured chapter digest by running a topology-C agentic pipeline: it resolves the target chapter, dispatches per-section analyst subagents to extract key concepts and formulas, fills coverage gaps via corpus retrieval and Wikipedia, and runs a judge loop to verify completeness before delivering the final ExtensionDigest.",
  features: [
    { label: "Topology-C pipeline", detail: "Resolve → fetch structure → per-section analysts → polish → augmentor → judge loop." },
    { label: "Per-section analysts", detail: "One analyst subagent per section extracts concepts, formulas, and structured notes in parallel." },
    { label: "Gap augmentation", detail: "Hybrid corpus retrieval and Wikipedia lookup fill coverage gaps flagged by the polishing stage." },
    { label: "Judge loop", detail: "Capped re-call loop: audits formula completeness and citation coverage before finalising the digest." },
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
