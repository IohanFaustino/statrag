import React, { useMemo, useState } from "react";
import type { QAAnswer, QAStoryAnswer, StoryCitation, TutorCitation } from "../types";
import { MathBlock } from "./Math";
import { renderInlineWithCites } from "./views/TutorView";

// ─── Shared Chip component (mirrors StoryDigestCard's Chip) ──────────────────

function Chip({ c }: { c: StoryCitation }) {
  if (c.kind === "wikipedia" && c.url) {
    return (
      <a className="citation-chip citation-chip--wiki" href={c.url}
         target="_blank" rel="noopener noreferrer">🌐 {c.label}</a>
    );
  }
  return <span className="citation-chip citation-chip--corpus" title={c.label}>📕 {c.label}</span>;
}

// ─── Discriminator ────────────────────────────────────────────────────────────
// Story shape: has intro AND conclusion, and text is absent/empty.
// Deepagent shape: has thesis/deepening/synthesis but no text.
// Legacy shape: has text.

function isStoryAnswer(answer: QAAnswer | QAStoryAnswer): answer is QAStoryAnswer {
  const a = answer as Record<string, unknown>;
  const hasIntro = typeof a["intro"] === "string";
  const hasConclusion = typeof a["conclusion"] === "string";
  const hasText = typeof a["text"] === "string" && (a["text"] as string).trim().length > 0;
  return hasIntro && hasConclusion && !hasText;
}

// ─── Component ────────────────────────────────────────────────────────────────

interface QAAnswerCardProps {
  answer: QAAnswer | QAStoryAnswer;
}

/**
 * Renders a Q&A answer in one of three shapes:
 *
 *  1. QAStoryAnswer — storytelling pipeline (intro, deepening, conclusion,
 *     StoryCitation[] with 📕/🌐 chips, [n] superscript pills in prose).
 *  2. Legacy QAAnswer — { text, scope, citations (TutorCitation[]) }.
 *  3. Deepagent QAAnswer — { thesis, deepening, synthesis } progression.
 *
 * All hooks are called unconditionally at the top level to satisfy React's
 * rules of hooks. Branches that don't use a value just compute something cheap.
 */
export default function QAAnswerCard({ answer }: QAAnswerCardProps) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const isStory = isStoryAnswer(answer);
  const story = answer as QAStoryAnswer;
  const qa = answer as QAAnswer;

  // ── Compute values for both paths (hooks must be unconditional) ──────────

  // Story path: build inline prose nodes for deepening
  const storyDeepening = isStory ? story.deepening : "";
  const storyCitations = isStory ? (story.citations ?? []) : [];

  const storyCitMap = useMemo(() => {
    const m = new Map<number, TutorCitation>();
    storyCitations.forEach((c, i) => {
      const idx = i + 1;
      m.set(idx, {
        index: idx,
        book_name: c.book_name ?? c.label,
        chapter: c.chapter ?? "",
        authors_short: c.authors ?? "",
        year: c.year,
      });
    });
    return m;
  }, [storyCitations]);

  const storyDeepeningNodes = useMemo(
    () => renderInlineWithCites(storyDeepening, storyCitMap, hoveredIdx, setHoveredIdx),
    [storyDeepening, storyCitMap, hoveredIdx],
  );
  // Intro + conclusion also flow through the guarded renderer so inline math /
  // [n] markers render (was raw string → leaked $…$ and bare \mu).
  const storyIntroNodes = useMemo(
    () => renderInlineWithCites(isStory ? story.intro : "", storyCitMap, hoveredIdx, setHoveredIdx),
    [isStory, story, storyCitMap, hoveredIdx],
  );
  const storyConclusionNodes = useMemo(
    () => renderInlineWithCites(isStory ? story.conclusion : "", storyCitMap, hoveredIdx, setHoveredIdx),
    [isStory, story, storyCitMap, hoveredIdx],
  );

  // Legacy/deepagent path: body text and citation map
  const legacyBodyText = useMemo(() => {
    if (isStory) return "";
    const { text } = qa;
    if (typeof text === "string" && text.trim()) return text;
    return [qa.thesis, qa.deepening, qa.synthesis]
      .filter((s): s is string => typeof s === "string" && s.trim().length > 0)
      .join("\n\n");
  }, [isStory, qa]);

  const legacyCitMap = useMemo(() => {
    if (isStory) return new Map<number, TutorCitation>();
    const m = new Map<number, TutorCitation>();
    for (const c of (qa.citations as TutorCitation[]) ?? []) m.set(c.index, c);
    return m;
  }, [isStory, qa]);

  const legacyBodyNodes = useMemo(
    () => renderInlineWithCites(legacyBodyText, legacyCitMap, hoveredIdx, setHoveredIdx),
    [legacyBodyText, legacyCitMap, hoveredIdx],
  );

  // ── Story render ─────────────────────────────────────────────────────────
  if (isStory) {
    const grounding = story.grounding;
    const grounded = grounding?.ok === true;
    const safeMathBlocks = story.math_blocks ?? [];
    const corpusCount = storyCitations.filter((c) => c.kind === "corpus").length;
    const wikiCount = storyCitations.filter((c) => c.kind === "wikipedia").length;

    return (
      <div className="qa-card qa-card--story">
        {story.intro?.trim() && <p className="qa-card__story-intro">{storyIntroNodes}</p>}
        <div className="qa-card__story-deepening">{storyDeepeningNodes}</div>
        {story.conclusion?.trim() && (
          <p className="qa-card__story-conclusion">{storyConclusionNodes}</p>
        )}

        {safeMathBlocks.length > 0 && (
          <div className="qa-card__math-blocks">
            {safeMathBlocks.map((tex, i) => (
              <div key={i} className="qa-card__math-block">
                <MathBlock tex={tex} />
              </div>
            ))}
          </div>
        )}

        {storyCitations.length > 0 && (
          <div className="qa-card__story-chips">
            {storyCitations.map((c, i) => <Chip key={i} c={c} />)}
          </div>
        )}

        {grounding && (
          <div className={"qa-card__badge" + (grounded ? " is-grounded" : " is-partial")}>
            {grounded ? "✓ grounded" : "⚠ partial"}
            {typeof grounding.confidence === "number" && (
              <span className="qa-card__conf"> ({Math.round(grounding.confidence * 100)}%)</span>
            )}
          </div>
        )}
        {grounding?.corpus_weak && (
          <p className="qa-card__corpus-weak-note">
            Not found in your textbooks — answered from Wikipedia
          </p>
        )}
        {grounding?.wiki_unavailable && (
          <p className="qa-card__wiki-unavailable-note">
            Wikipedia context unavailable
          </p>
        )}
      </div>
    );
  }

  // ── Legacy / deepagent render ─────────────────────────────────────────────
  const { scope, grounding, math_blocks } = qa;
  const grounded = grounding?.ok === true;
  const assumedKnown = scope?.assumed_known ?? [];
  const safeMathBlocks = math_blocks ?? [];

  return (
    <div className="qa-card">
      {scope?.target_gap && (
        <div className="qa-card__scope">
          <span className="qa-card__scope-lbl">Answering:</span>{" "}
          <span className="qa-card__gap">{scope.target_gap}</span>
          {assumedKnown.length > 0 && (
            <span className="qa-card__known">
              {" · assuming you know: "}
              {assumedKnown.join(", ")}
            </span>
          )}
        </div>
      )}
      <div className="qa-card__body">{legacyBodyNodes}</div>
      {safeMathBlocks.length > 0 && (
        <div className="qa-card__math-blocks">
          {safeMathBlocks.map((tex, i) => (
            <div key={i} className="qa-card__math-block">
              <MathBlock tex={tex} />
            </div>
          ))}
        </div>
      )}
      {grounding && (
        <div className={"qa-card__badge" + (grounded ? " is-grounded" : " is-partial")}>
          {grounded ? "✓ grounded" : "⚠ partial"}
          {typeof grounding.confidence === "number" && (
            <span className="qa-card__conf"> ({Math.round(grounding.confidence * 100)}%)</span>
          )}
        </div>
      )}
    </div>
  );
}
