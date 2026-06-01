import { useState } from "react";
import type { FacilitateDigest, ConceptAnchor } from "../types";
import ConceptModal from "./ConceptModal";
import FacilitateContent from "./FacilitateContent";

export default function FacilitateDigestCard({ digest }: { digest: FacilitateDigest }) {
  const [active, setActive] = useState<ConceptAnchor | null>(null);
  const conf = digest.grounding?.confidence ?? 0;
  const grounded = digest.grounding?.ok === true && conf >= 0.7;
  return (
    <div className="chapter-card chapter-card--facilitate">
      <div className="chapter-card__hd">
        <span className="chapter-card__mode">Facilitate</span>
        <span className="chapter-card__scope">{digest.scope.book_slug} · {digest.scope.chapter_id}</span>
        <span className={`chapter-card__badge ${grounded ? "is-ok" : "is-partial"}`}>
          {grounded ? "✓ grounded" : "⚠ partial"}
        </span>
      </div>
      {digest.intro && <p className="chapter-card__intro">{digest.intro}</p>}
      <div className="chapter-card__blocks">
        {digest.blocks.map((b, i) => (
          <section key={`${b.section_id}-${i}`} className="chapter-block">
            <h3 className="chapter-block__h">{b.h2_path}</h3>
            {b.page_from > 0 && (
              <span className="chapter-block__pages">
                pp. {b.page_from}{b.page_to > b.page_from ? `–${b.page_to}` : ""}
              </span>
            )}
            <div className="chapter-block__body"><FacilitateContent text={b.body} concepts={b.concepts} onPick={setActive} /></div>
          </section>
        ))}
      </div>
      {digest.outro && <p className="chapter-card__outro">{digest.outro}</p>}
      {active && <ConceptModal anchor={active} onClose={() => setActive(null)} />}
    </div>
  );
}
