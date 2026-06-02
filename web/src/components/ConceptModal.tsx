import { useEffect } from "react";
import type { ConceptAnchor } from "../types";
import FacilitateContent, { MathText } from "./FacilitateContent";

interface Props { anchor: ConceptAnchor; onClose: () => void; }

export default function ConceptModal({ anchor, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const p = anchor.provenance;
  const prov = [p.authors_short, p.section, p.page_from > 0 ? `p. ${p.page_from}` : ""]
    .filter(Boolean).join(" · ");
  return (
    <div className="concept-modal__overlay" data-testid="concept-modal-overlay" onClick={onClose}>
      <div className="concept-modal" role="dialog" aria-label={anchor.term}
           onClick={(e) => e.stopPropagation()}>
        <div className="concept-modal__hd">
          <span className={`concept-modal__kind concept-modal__kind--${anchor.kind}`}>{anchor.kind}</span>
          <h3 className="concept-modal__term"><MathText text={anchor.term} /></h3>
          <button className="concept-modal__close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="concept-modal__body">
          <FacilitateContent text={anchor.explanation} />
        </div>
        {prov && (
          <p className="concept-modal__prov">
            {prov}
            {p.fallback && <span className="concept-modal__note"> · from this section</span>}
            {!p.same_author && <span className="concept-modal__note"> · other author</span>}
          </p>
        )}
      </div>
    </div>
  );
}
