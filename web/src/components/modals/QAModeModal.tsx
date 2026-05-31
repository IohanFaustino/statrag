import FocusModal from "./FocusModal";
import QAPipeline from "../QAPipeline";

interface QAModeModalProps {
  open: boolean;
  onClose(): void;
}

export default function QAModeModal({ open, onClose }: QAModeModalProps) {
  if (!open) return null;
  return (
    <FocusModal open={open} onClose={onClose} labelledBy="qa-modal-title">
      <div className="about-modal">
        <div className="about-modal__hd">
          <h2 id="qa-modal-title" className="about-modal__title">
            Q&amp;A mode
          </h2>
          <button
            type="button"
            className="about-modal__close"
            aria-label="Close"
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        <p className="about-modal__blurb">
          Punctual Q&amp;A: scope → retrieve → generate → verify
        </p>
        <QAPipeline />
      </div>
    </FocusModal>
  );
}
