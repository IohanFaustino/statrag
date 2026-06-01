import React, { useState } from "react";
import type { FacilitateDigest, ConceptAnchor, FacilitateBlock } from "../types";
import ConceptModal from "./ConceptModal";
import { renderInlineWithCites } from "./views/TutorView";

const ANCHOR_RE = /\[\[(c\d+)\]\]/g;
const EMPTY_CITES = new Map();

function renderBody(block: FacilitateBlock, onPick: (a: ConceptAnchor) => void) {
  const byId = new Map(block.concepts.map((c) => [c.id, c]));
  const out: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  ANCHOR_RE.lastIndex = 0;
  while ((m = ANCHOR_RE.exec(block.body))) {
    if (m.index > last) {
      const segment = block.body.slice(last, m.index);
      const nodes = renderInlineWithCites(segment, EMPTY_CITES, null, () => {});
      for (const node of nodes) out.push(<React.Fragment key={`t${k++}`}>{node}</React.Fragment>);
    }
    const c = byId.get(m[1]);
    if (c) {
      out.push(
        <button key={`a${k++}`} type="button"
          className={`concept-anchor concept-anchor--${c.kind}`}
          onClick={() => onPick(c)}>{c.term}</button>,
      );
    } else {
      out.push(m[0]);
    }
    last = m.index + m[0].length;
  }
  if (last < block.body.length) {
    const segment = block.body.slice(last);
    const nodes = renderInlineWithCites(segment, EMPTY_CITES, null, () => {});
    for (const node of nodes) out.push(<React.Fragment key={`t${k++}`}>{node}</React.Fragment>);
  }
  return out;
}

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
            {b.key_points.length > 0 && (
              <ul className="facilitate-keypoints">
                {b.key_points.map((kp, j) => <li key={j}>{kp}</li>)}
              </ul>
            )}
            <div className="chapter-block__body">{renderBody(b, setActive)}</div>
          </section>
        ))}
      </div>
      {digest.outro && <p className="chapter-card__outro">{digest.outro}</p>}
      {active && <ConceptModal anchor={active} onClose={() => setActive(null)} />}
    </div>
  );
}
