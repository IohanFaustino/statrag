import React, { useState } from "react";
import type { FacilitateStory, ConceptAnchor, Movement } from "../types";
import FacilitateContent from "./FacilitateContent";

interface Props {
  story: FacilitateStory;
  onConcept?: (a: ConceptAnchor) => void;
}

export default function FacilitateStoryCard({ story, onConcept }: Props) {
  const concepts = story.concepts;
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      const res = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(story),
      });
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const cd = res.headers.get("content-disposition");
      const match = cd?.match(/filename="?([^"]+)"?/);
      a.download = match?.[1] || "facilitate-story.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setIsDownloading(false);
    }
  };

  const renderMovement = (m: Movement, i: number) => {
    if (m.formal) {
      const f = m.formal;
      return (
        <div className="fstory__formal" key={i}>
          <span className={`fstory__kind fstory__kind--${f.kind}`}>{f.kind}</span>
          <blockquote className="fstory__statement">
            <FacilitateContent text={f.statement} />
          </blockquote>
          <div className="fstory__unpack">
            <FacilitateContent text={f.explanation} concepts={concepts} onPick={onConcept} />
          </div>
        </div>
      );
    }
    return (
      <div className="fstory__movement" key={i}>
        <FacilitateContent text={m.prose} concepts={concepts} onPick={onConcept} />
      </div>
    );
  };

  return (
    <div className="fstory" data-testid="facilitate-story">
      <div className="fstory__hd">
        <span className="fstory__hd-label">Facilitate</span>
        <button type="button" className="fstory__download" onClick={handleDownload} disabled={isDownloading} aria-label="Download ZIP" title="Download ZIP">{isDownloading ? "…" : "↓"}</button>
      </div>
      {story.hook && (
        <div className="fstory__hook">
          <FacilitateContent text={story.hook} concepts={concepts} onPick={onConcept} />
        </div>
      )}
      <div className="fstory__body">{story.movements.map(renderMovement)}</div>
      {story.takeaway && (
        <div className="fstory__takeaway">
          <FacilitateContent text={story.takeaway} concepts={concepts} onPick={onConcept} />
        </div>
      )}
      {story.citations.length > 0 && (
        <div className="fstory__cites">
          {story.citations.map((c, i) =>
            c.url ? (
              <a key={i} className="fstory__chip" href={c.url} target="_blank" rel="noreferrer">
                {c.kind === "wikipedia" ? "🌐" : "📕"} {c.label}
              </a>
            ) : (
              <span key={i} className="fstory__chip">📕 {c.label}</span>
            )
          )}
        </div>
      )}
      {story.grounding && story.grounding.ok === false && (
        <div className="fstory__warn">⚠ Some content may not be fully grounded.</div>
      )}
    </div>
  );
}
