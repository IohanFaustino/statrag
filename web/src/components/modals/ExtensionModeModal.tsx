import FocusModal from "./FocusModal";
import ExtensionPipelineDiagram from "../ExtensionPipelineDiagram";

const EXTENSION_MODE = {
  title: "Extension mode",
  blurb: "Story digest with curiosity boxes — deterministic async pipeline over the chapter's sections",
  description:
    "Extension mode produces a story digest via a deterministic async pipeline. It resolves the scoped book/chapter sections, then a storyteller turns each section into a take (2–4 short paragraphs, plain-text heading, bridging from the previous take), a story editor stitches takes into one continuous narrative with an explicit through-line, a subject miner extracts curiosity subjects per take (gap taxonomy: formal-def / derivation / comparative / application / history), a PURE-CODE researcher gathers cross-book corpus evidence (hybrid search, rerank, score floor) plus Wikipedia REST summaries, a curiosity writer drafts evidence-grounded bullets (emitting only evidence ids), a PURE-CODE citation binder copies citation fields VERBATIM from retrieval payloads (unverifiable bullets dropped to unfilled_subjects), and a judge runs one bounded retry for under-covered takes before emitting the final StoryDigest (timeline rail + per-take curiosity boxes + ZIP export with per-take footnotes).",
  features: [
    { label: "Story timeline", detail: "1 section = 1 take. Takes follow the author's sequence, rendered as multi-paragraph justified prose with a narrative through-line stitched by the story editor." },
    { label: "Curiosity boxes", detail: "Per-take collapsed toggle. Each box shows evidence-grounded bullets with corpus (📕) and Wikipedia (🌐) citation chips. Bullets without verified evidence are dropped." },
    { label: "Verbatim citations", detail: "The citation binder is pure code — citation fields are copied directly from retrieval payloads, never written by a model. Uncited bullets are moved to unfilled_subjects." },
    { label: "Judge + bounded retry", detail: "Per-take coverage check after the first curiosity pass. If a take is under-covered, the pipeline runs ONE retry (mine → research → write) and lists remaining gaps in unfilled_subjects." },
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
