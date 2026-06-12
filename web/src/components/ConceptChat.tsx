import { useEffect, useRef, useState } from "react";
import type { ConceptAnchor, StoryCitation } from "../types";

interface Props { anchor: ConceptAnchor; conversationId: string; onClose(): void; }
interface Turn { role: "user" | "assistant"; text: string; citations?: StoryCitation[]; }

async function streamExplore(body: object, onEvent: (e: Record<string, unknown>) => void) {
  const resp = await fetch("/api/concept/explore", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (!resp.ok || !resp.body) return;
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split(/\r?\n\r?\n/);
    buf = parts.pop() || "";
    for (const p of parts) {
      const line = p.split(/\r?\n/).find((l) => l.startsWith("data:"));
      if (line) { try { onEvent(JSON.parse(line.slice(5).trim())); } catch { /* ignore */ } }
    }
  }
}

export default function ConceptChat({ anchor, conversationId, onClose }: Props) {
  const bookSlug = anchor.provenance?.book_slug || "";
  const sectionId = anchor.provenance?.section || "";
  const [turns, setTurns] = useState<Turn[]>([]);
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(true);
  const seeded = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    if (seeded.current) return;
    seeded.current = true;
    streamExplore({ term: anchor.term, kind: anchor.kind, book_slug: bookSlug,
      section_id: sectionId, conversationId }, (e) => {
        if (!mounted.current) return;
        if (e.type === "concept_seed")
          setTurns([{ role: "assistant", text: e.brief as string, citations: e.citations as StoryCitation[] }]);
      }).finally(() => { if (mounted.current) setLoading(false); });
  }, [anchor.term, anchor.kind, bookSlug, sectionId, conversationId]);

  function deepen(text: string) {
    const v = text.trim(); if (!v) return;
    const history = [...turns.map((t) => ({ role: t.role, text: t.text })), { role: "user", text: v }];
    setTurns((p) => [...p, { role: "user", text: v }]); setValue(""); setLoading(true);
    streamExplore({ term: anchor.term, kind: anchor.kind, book_slug: bookSlug,
      section_id: sectionId, conversationId, history }, (e) => {
        if (!mounted.current) return;
        if (e.type === "concept_followup")
          setTurns((p) => [...p, { role: "assistant", text: e.brief as string, citations: e.citations as StoryCitation[] }]);
      }).finally(() => { if (mounted.current) setLoading(false); });
  }

  return (
    <div className="concept-chat" role="dialog" aria-label={anchor.term}>
      <header className="concept-chat__hd">
        <div className="concept-chat__hd-left">
          <span className="concept-chat__badge">CONCEPT</span>
          <span className="concept-chat__title">{anchor.term}</span>
        </div>
        <div className="concept-chat__hd-right">
          <button
            className="concept-chat__close"
            type="button"
            onClick={onClose}
            aria-label="Close concept chat"
          >
            <svg
              viewBox="0 0 16 16"
              width="12"
              height="12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="m4 4 8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
      </header>
      <div className="concept-chat__body">
        {turns.map((t, i) => (
          <div key={i} className={`concept-chat__turn concept-chat__turn--${t.role}`}>
            <p>{t.text}</p>
            {t.citations && t.citations.length > 0 && (
              <div className="concept-chat__cites">
                {t.citations.map((c, j) => c.url
                  ? <a key={j} href={c.url} target="_blank" rel="noreferrer">{c.kind === "wikipedia" ? "🌐" : "📕"} {c.label}</a>
                  : <span key={j}>📕 {c.label}</span>)}
              </div>
            )}
          </div>
        ))}
        {loading && <div className="concept-chat__loading">…</div>}
      </div>
      <div className="concept-chat__input">
        <div className="concept-chat__field">
          <textarea
            value={value}
            placeholder="Ask to go deeper on this concept…"
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); deepen(value); } }}
            rows={1}
            aria-label="Concept question input"
          />
        </div>
        <span className="concept-chat__foot">grounded in your books + Wikipedia</span>
      </div>
    </div>
  );
}
