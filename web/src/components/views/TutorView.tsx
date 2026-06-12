import React, { useEffect, useState } from "react";

import type { TutorAnswer, TutorCitation } from "../../types";
import { MathBlock, MathInline } from "../Math";

interface Props {
  data: TutorAnswer;
}

/**
 * T19 — render a TutorAnswer with:
 *   - markdown-ish prose split into ## H2 sections;
 *   - inline `[N]` markers re-mapped to clickable citation pills;
 *   - inline `$...$` and block `$$...$$` math via the existing MathInline;
 *   - a Sources panel built from `data.citations`, anchored to `#cite-N`.
 *
 * Kept dependency-free (no marked / react-markdown) so the chat bundle stays
 * lean. The renderer handles `## ` headings, bold `**…**`, inline math, and
 * block math; everything else flows as plain paragraphs.
 */
interface Section {
  title: string | null;
  body: Block[];
}

function groupSections(blocks: Block[]): Section[] {
  const sections: Section[] = [];
  let current: Section = { title: null, body: [] };
  for (const b of blocks) {
    if (b.kind === "h2") {
      if (current.title !== null || current.body.length > 0) sections.push(current);
      current = { title: b.text, body: [] };
    } else {
      current.body.push(b);
    }
  }
  if (current.title !== null || current.body.length > 0) sections.push(current);
  return sections;
}

export default function TutorView({ data }: Props) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState<boolean>(false);

  // Deep-link: if the URL hash is ``#cite-<N>`` open the sources panel and
  // scroll to the matching citation once it is in the DOM. Listens to
  // ``hashchange`` so the behaviour also fires when the user clicks a
  // citation marker inside the answer.
  useEffect(() => {
    const apply = () => {
      const h = (typeof window !== "undefined" && window.location.hash) || "";
      const m = h.match(/^#cite-(\d+)$/);
      if (!m) return;
      const idx = Number(m[1]);
      const present = (data.citations ?? []).some((c) => c.index === idx);
      if (!present) return;
      setSourcesOpen(true);
      // Wait for the <li id="cite-N"> to mount, then scroll.
      window.setTimeout(() => {
        const el = document.getElementById(`cite-${idx}`);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          setHoveredIdx(idx);
        }
      }, 50);
    };
    apply();
    window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, [data.citations]);

  const [openSections, setOpenSections] = useState<Set<number>>(() => {
    // Auto-expand the Introduction section on initial render.
    // Compute sections from data.text so we don't hardcode index 0.
    const initBlocks = splitIntoBlocks(data.text || "");
    const initSections = groupSections(initBlocks);
    const introIdx = initSections.findIndex((s) => {
      if (s.title === null) return false;
      const t = s.title.trim().toLowerCase();
      return t === "introduction" || t === "tl;dr"; // tl;dr = legacy convs
    });
    return introIdx >= 0 ? new Set([introIdx]) : new Set();
  });

  // Anchor-on-hash: when URL hash is ``#fig-N`` open every collapsible
  // section so the target ``<figure id="fig-N">`` is in the DOM, then
  // scroll it into view.
  useEffect(() => {
    const apply = () => {
      const h = (typeof window !== "undefined" && window.location.hash) || "";
      const m = h.match(/^#fig-(\d+)$/);
      if (!m) return;
      setOpenSections((prev) => {
        const all = new Set(prev);
        for (let s = 0; s < 32; s++) all.add(s);
        return all;
      });
      window.setTimeout(() => {
        const el = document.getElementById(`fig-${m[1]}`);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 80);
    };
    apply();
    window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, []);
  const toggleSection = (i: number) =>
    setOpenSections((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  // Click a [N] marker → open the Sources panel and scroll to that source,
  // independent of the URL hash (clicking the same marker twice would not fire
  // hashchange). Also keeps the deep-link hash in sync.
  const onCite = React.useCallback((idx: number) => {
    const present = (data.citations ?? []).some((c) => c.index === idx);
    if (!present) return;
    setSourcesOpen(true);
    if (typeof window !== "undefined") {
      try { window.history.replaceState(null, "", `#cite-${idx}`); } catch { /* ignore */ }
    }
    window.setTimeout(() => {
      const el = document.getElementById(`cite-${idx}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        setHoveredIdx(idx);
      }
    }, 60);
  }, [data.citations]);

  const citationsByIndex = React.useMemo(() => {
    const m = new Map<number, TutorCitation>();
    for (const c of data.citations ?? []) m.set(c.index, c);
    return m;
  }, [data.citations]);

  const blocks = splitIntoBlocks(data.text || "");
  const sections = groupSections(blocks);
  let figureCounter = 0;

  const renderBlock = (block: Block, key: number) => {
    if (block.kind === "math") {
      return (
        <div key={key} className="tutor-view__math-block">
          <MathBlock tex={block.tex} />
        </div>
      );
    }
    if (block.kind === "image") {
      figureCounter += 1;
      const figId = `fig-${figureCounter}`;
      return (
        <figure key={key} id={figId} className="tutor-view__figure">
          <img src={block.url} alt={block.alt} loading="lazy" style={{ maxWidth: "100%", height: "auto", display: "block", borderRadius: 4 }} />
          {block.alt ? <figcaption className="tutor-view__figcaption" style={{ fontSize: "0.85em", opacity: 0.7, marginTop: 4 }}>{block.alt}</figcaption> : null}
        </figure>
      );
    }
    if (block.kind === "h3") {
      // Centered subsection header inside a section body, flanked by dashes
      // (rendered via CSS ::before/::after). No toggle.
      return (
        <h3 key={key} className="tutor-view__h3">
          {renderInlineWithCites(block.text, citationsByIndex, hoveredIdx, setHoveredIdx, onCite)}
        </h3>
      );
    }
    if (block.kind === "quote") {
      return (
        <blockquote key={key} className="tutor-view__quote">
          {renderInlineWithCites(block.text, citationsByIndex, hoveredIdx, setHoveredIdx, onCite)}
        </blockquote>
      );
    }
    if (block.kind === "list") {
      const Tag = block.ordered ? "ol" : "ul";
      return (
        <Tag key={key} className="tutor-view__list" style={{ paddingLeft: "1.4em", margin: "0.4em 0" }}>
          {block.items.map((it, k) => (
            <li key={k}>{renderInlineWithCites(it, citationsByIndex, hoveredIdx, setHoveredIdx, onCite)}</li>
          ))}
        </Tag>
      );
    }
    return (
      <p key={key} className="tutor-view__para">
        {renderInlineWithCites(block.text, citationsByIndex, hoveredIdx, setHoveredIdx, onCite)}
      </p>
    );
  };

  return (
    <div className="tutor-view">
      {sections.map((section, sIdx) => {
        const open = openSections.has(sIdx);
        if (section.title === null) {
          return (
            <div key={`sec-${sIdx}`} className="tutor-view__section tutor-view__section--lead">
              {section.body.map((b, j) => renderBlock(b, j))}
            </div>
          );
        }
        return (
          <section key={`sec-${sIdx}`} className="tutor-view__section">
            <button
              type="button"
              className="tutor-view__h2 tutor-view__h2--toggle"
              aria-expanded={open}
              onClick={() => toggleSection(sIdx)}
            >
              {/* Rotating chevron — 0° collapsed, 90° expanded */}
              <span
                aria-hidden="true"
                style={{
                  display: "inline-block",
                  marginRight: "0.4em",
                  transform: open ? "rotate(90deg)" : "rotate(0deg)",
                  transition: "transform 180ms ease-out",
                }}
                className="tutor-view__chevron"
              >
                ▸
              </span>
              <span className="tutor-view__h2-text">{section.title}</span>
            </button>
            {/* Always-mounted wrapper — animated via max-height + opacity */}
            <div
              className="tutor-view__section-body-wrapper"
              style={{
                overflow: "hidden",
                maxHeight: open ? "4000px" : "0px",
                opacity: open ? 1 : 0,
                transition: open
                  ? "max-height 220ms ease-out, opacity 180ms ease-out"
                  : "max-height 220ms ease-in, opacity 150ms ease-in",
              }}
            >
              <div className="tutor-view__section-body">
                {section.body.map((b, j) => renderBlock(b, j))}
              </div>
            </div>
          </section>
        );
      })}

      {(data.citations?.length ?? 0) > 0 && (
        <div className="tutor-view__sources">
          <button
            type="button"
            className="tutor-view__sources-toggle"
            aria-expanded={sourcesOpen}
            onClick={() => setSourcesOpen((v) => !v)}
          >
            <span
              className={
                sourcesOpen
                  ? "tutor-view__sources-chevron tutor-view__sources-chevron--open"
                  : "tutor-view__sources-chevron"
              }
              aria-hidden="true"
            >
              ›
            </span>
            <span>References</span>
            <span className="tutor-view__sources-count">
              ({data.citations?.length ?? 0})
            </span>
          </button>
          {sourcesOpen && (
            <ol className="tutor-view__sources-list">
              {(data.citations ?? []).map((c) => (
                <li
                  key={c.index}
                  id={`cite-${c.index}`}
                  className={
                    hoveredIdx === c.index
                      ? "tutor-view__src tutor-view__src--hover"
                      : "tutor-view__src"
                  }
                >
                  <span className="tutor-view__src-num">[{c.index}]</span>{" "}
                  <span className="tutor-view__src-meta">
                    {formatApa(c)}
                  </span>
                  {c.quote ? (
                    <div className="tutor-view__src-quote">“{c.quote}”</div>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

// ─── helpers ──────────────────────────────────────────────────────────────

type Block =
  | { kind: "h2"; text: string }
  | { kind: "h3"; text: string }
  | { kind: "para"; text: string }
  | { kind: "math"; tex: string }
  | { kind: "image"; alt: string; url: string }
  | { kind: "quote"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] };

export function splitIntoBlocks(text: string): Block[] {
  const out: Block[] = [];
  const lines = text.split("\n");

  let buffer: string[] = [];
  let inMath = false;
  let mathBuf: string[] = [];
  let listBuf: { ordered: boolean; items: string[] } | null = null;
  let quoteBuf: string[] | null = null;

  const flushPara = () => {
    const joined = buffer.join("\n").trim();
    if (joined) out.push({ kind: "para", text: joined });
    buffer = [];
  };
  const flushList = () => {
    if (listBuf && listBuf.items.length) {
      out.push({ kind: "list", ordered: listBuf.ordered, items: listBuf.items });
    }
    listBuf = null;
  };
  const flushQuote = () => {
    if (quoteBuf && quoteBuf.length) {
      out.push({ kind: "quote", text: quoteBuf.join("\n").trim() });
    }
    quoteBuf = null;
  };

  const LIST_RE = /^\s*(?:([-*+])|(\d+)\.)\s+(.*)$/;
  const QUOTE_RE = /^\s*>\s?(.*)$/;

  for (const line of lines) {
    if (inMath) {
      if (line.trim().endsWith("$$")) {
        const last = line.trim().slice(0, -2).trim();
        if (last) mathBuf.push(last);
        out.push({ kind: "math", tex: mathBuf.join("\n").trim() });
        mathBuf = [];
        inMath = false;
      } else {
        mathBuf.push(line);
      }
      continue;
    }
    const stripped = line.trim();
    const listMatch = line.match(LIST_RE);
    if (listMatch) {
      flushPara();
      const ordered = !!listMatch[2];
      if (!listBuf || listBuf.ordered !== ordered) {
        flushList();
        listBuf = { ordered, items: [] };
      }
      listBuf.items.push(listMatch[3].trim());
      continue;
    } else if (listBuf) {
      flushList();
    }
    const quoteMatch = line.match(QUOTE_RE);
    if (quoteMatch) {
      flushPara();
      if (!quoteBuf) quoteBuf = [];
      quoteBuf.push(quoteMatch[1]);
      continue;
    } else if (quoteBuf) {
      flushQuote();
    }
    const imgMatch = stripped.match(/^!\[(.*?)\]\((.*?)\)\s*$/);
    if (imgMatch) {
      flushPara();
      out.push({ kind: "image", alt: imgMatch[1], url: imgMatch[2] });
      continue;
    }
    if (stripped.startsWith("### ")) {
      flushList();
      flushPara();
      out.push({ kind: "h3", text: stripped.slice(4).trim() });
    } else if (stripped.startsWith("## ")) {
      flushPara();
      const heading = stripped.slice(3).trim();
      // T22 (E4): once the LLM emits its own `## Sources` block, stop
      // parsing — the sources panel below renders sources from the
      // structured citations array, so the duplicate prose must go.
      if (heading.toLowerCase() === "sources") {
        break;
      }
      out.push({ kind: "h2", text: heading });
    } else if (stripped.startsWith("$$") && stripped.endsWith("$$") && stripped.length > 4) {
      flushPara();
      out.push({ kind: "math", tex: stripped.slice(2, -2).trim() });
    } else if (stripped.startsWith("$$")) {
      flushPara();
      inMath = true;
      mathBuf.push(stripped.slice(2));
    } else if (stripped.startsWith("\\[") && stripped.endsWith("\\]") && stripped.length > 4) {
      flushPara();
      out.push({ kind: "math", tex: stripped.slice(2, -2).trim() });
    } else if (stripped === "") {
      flushPara();
    } else {
      buffer.push(line);
    }
  }
  flushList();
  flushQuote();
  flushPara();
  return out;
}

// ─── Math delimiter normalizer ────────────────────────────────────────────────
//
// The LLM sometimes emits malformed / mixed math delimiters such as:
//   \$(   instead of  \(      (stray dollar sign adjacent to escaped paren)
//   \$)   instead of  \)
//   \($p(D\mid\theta)$\)      ($…$ nested INSIDE \(…\))
//
// This function repairs those before the inline parser runs, using a small
// state machine.  Rules (applied left-to-right, single pass):
//
//   1. \$( → \(   and  \$) → \)
//      Literal sequences "\" "$" "(" / ")" where the dollar is spurious.
//
//   2. Inside an open \(…\) or \[…\] span, any bare $ that is NOT part of
//      a closing \) / \] is stripped, because the LLM sometimes writes
//      \($inner$\) meaning the whole thing is one math span.
//      We do NOT strip $…$ that live outside an already-open LaTeX span,
//      because those are legitimate inline math.
//
// Edge cases deliberately NOT handled (too risky to break clean text):
//   - $$…$$ display blocks that contain \(…\) — extremely rare
//   - Mismatched closer types (\( … \])
//
export function normalizeMathDelimiters(text: string): string {
  // Some persisted answers carry ESC (0x1B) control chars where a LaTeX
  // backslash was lost (e.g. "\x1bmu" / "\x1bge" instead of "\mu" / "\ge"),
  // which KaTeX renders as a tofu box. Restore the backslash.
  text = text.replace(/\x1b/g, "\\");
  const out: string[] = [];
  let i = 0;
  // Track whether we are inside a \(…\) or \[…\] span.
  // "paren" = \(…\), "bracket" = \[…\]
  type LaTeXMode = "paren" | "bracket" | null;
  let latexMode: LaTeXMode = null;

  while (i < text.length) {
    // ── Rule 1a: \$( → \(  (backslash + dollar + open-paren)
    if (
      text[i] === "\\" &&
      text[i + 1] === "$" &&
      text[i + 2] === "("
    ) {
      out.push("\\(");
      i += 3;
      latexMode = "paren";
      continue;
    }
    // ── Rule 1b: \$) → \)  (backslash + dollar + close-paren)
    if (
      text[i] === "\\" &&
      text[i + 1] === "$" &&
      text[i + 2] === ")"
    ) {
      out.push("\\)");
      i += 3;
      latexMode = null;
      continue;
    }
    // ── Detect opening \(
    if (text[i] === "\\" && text[i + 1] === "(") {
      out.push("\\(");
      i += 2;
      latexMode = "paren";
      continue;
    }
    // ── Detect closing \)  (only meaningful when in "paren" mode)
    if (text[i] === "\\" && text[i + 1] === ")") {
      out.push("\\)");
      i += 2;
      // Consume a spurious trailing $ from the malformed "\)$" closer the
      // LLM pairs with the "\$(" opener (e.g. \$( \theta \)$ → \( \theta \)).
      if (text[i] === "$") i += 1;
      latexMode = null;
      continue;
    }
    // ── Detect opening \[
    if (text[i] === "\\" && text[i + 1] === "[") {
      out.push("\\[");
      i += 2;
      latexMode = "bracket";
      continue;
    }
    // ── Detect closing \]  (only meaningful when in "bracket" mode)
    if (text[i] === "\\" && text[i + 1] === "]") {
      out.push("\\]");
      i += 2;
      if (text[i] === "$") i += 1; // mirror the "\]$" closer repair
      latexMode = null;
      continue;
    }
    // ── Rule 2: bare $ inside an open LaTeX span
    //    Strip it (it's a spurious inner delimiter, e.g. \($expr$\) → \(expr\))
    if (text[i] === "$" && latexMode !== null) {
      // Skip this dollar — it doesn't belong inside \(…\)
      i += 1;
      continue;
    }
    // ── Everything else: copy verbatim
    out.push(text[i]);
    i += 1;
  }

  return out.join("");
}

const LATEX_COMMANDS = new Set<string>([
  "theta", "Theta", "vartheta",
  "nabla", "partial", "infty",
  "alpha", "beta", "gamma", "Gamma", "delta", "Delta",
  "epsilon", "varepsilon", "zeta", "eta", "iota", "kappa",
  "lambda", "Lambda", "mu", "nu", "xi", "Xi", "pi", "Pi",
  "rho", "varrho", "sigma", "Sigma", "tau", "upsilon", "Upsilon",
  "phi", "varphi", "Phi", "chi", "psi", "Psi", "omega", "Omega",
  "mathbb", "mathcal", "mathbf", "mathrm", "mathit", "mathsf", "mathtt",
  "hat", "widehat", "tilde", "widetilde", "bar", "overline", "underline",
  "vec", "dot", "ddot",
  "frac", "sqrt", "sum", "int", "prod", "lim", "sup", "inf", "min", "max",
  "log", "ln", "exp", "sin", "cos", "tan", "cot", "sec", "csc",
  "arcsin", "arccos", "arctan",
  "operatorname", "text", "textbf", "textit", "textrm", "emph",
  "leq", "geq", "neq", "approx", "equiv", "sim", "propto",
  "cdot", "times", "div", "pm", "mp",
  "quad", "qquad",
  "to", "leftarrow", "rightarrow", "leftrightarrow", "Rightarrow", "Leftrightarrow",
  "left", "right", "begin", "end", "over",
  "langle", "rangle", "lceil", "rceil", "lfloor", "rfloor",
  "forall", "exists", "in", "notin", "subset", "supset", "cup", "cap", "emptyset",
  "binom", "choose", "sout", "cancel", "colon",
  "ldots", "cdots", "vdots", "ddots",
  "boldsymbol", "bm", "ell",
  "big", "Big", "bigg", "Bigg",
  "bigl", "bigr", "Bigl", "Bigr", "biggl", "biggr", "Biggl", "Biggr",
]);

export function renderInlineWithCites(
  text: string,
  cites: Map<number, TutorCitation>,
  hoveredIdx: number | null,
  setHovered: (n: number | null) => void,
  onCite?: (idx: number) => void,
): React.ReactNode[] {
  // Repair malformed delimiters from the LLM before tokenising.
  text = normalizeMathDelimiters(text);
  // If single-`$` delimiters are unbalanced (odd count, ignoring escaped `\$`),
  // disable `$…$` math tokenising for this text — feeding a half-open span to
  // KaTeX produces glommed-glyph soup. `[N]` citations + bare-command auto-wrap
  // still work; a stray `$` just renders as a literal character.
  const dollarsBalanced = ((text.match(/(?<!\\)\$/g) || []).length % 2) === 0;
  // Tokenise on `[N]` markers and inline `$…$` math.
  const out: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < text.length) {
    const ch = text[i];
    const figMatch = text.slice(i).match(
      /^\[(?:F|Figure|Fig|Image|Img)\s*#?\s*(\d+)\]/i,
    );
    if (ch === "[" && figMatch) {
      const idx = parseInt(figMatch[1], 10);
      out.push(
        <a
          key={key++}
          href={`#fig-${idx}`}
          className="tutor-view__pill tutor-view__pill--fig"
          title={`Figure ${idx}`}
        >
          [F{idx}]
        </a>,
      );
      i += figMatch[0].length;
      continue;
    }
    // Citation marker: single [N], comma list [1, 2], or dash range [1]–[3].
    // Regex matches e.g. [1], [1, 2], [1,2,3], [1–3], [1-3], [1, 2-4].
    // Malformed markers ([1,], [], [1, x]) fall through to literal text.
    if (ch === "[" && /^\[\s*\d+(\s*[,–\-]\s*\d+)*\s*\]/.test(text.slice(i))) {
      const m = text.slice(i).match(/^\[\s*(\d+(?:\s*[,–\-]\s*\d+)*)\s*\]/)!;
      // Parse all individual indices from the matched interior.
      const interior = m[1];
      // Split on commas and dashes/en-dashes; expand ranges.
      const indices: number[] = [];
      // Tokenise by commas first, then handle each segment.
      const segments = interior.split(/\s*,\s*/);
      for (const seg of segments) {
        const rangeParts = seg.split(/\s*[–\-]\s*/);
        if (rangeParts.length === 2) {
          const from = parseInt(rangeParts[0], 10);
          const to = parseInt(rangeParts[1], 10);
          if (!isNaN(from) && !isNaN(to) && to >= from) {
            for (let n = from; n <= to; n++) indices.push(n);
          } else {
            // Not a valid range — treat as two discrete numbers
            if (!isNaN(from)) indices.push(from);
            if (!isNaN(to)) indices.push(to);
          }
        } else {
          const n = parseInt(rangeParts[0], 10);
          if (!isNaN(n)) indices.push(n);
        }
      }
      for (let pi = 0; pi < indices.length; pi++) {
        const idx = indices[pi];
        const cite = cites.get(idx);
        if (pi > 0) {
          out.push(<span key={key++}>{","}</span>);
        }
        out.push(
          <a
            key={key++}
            href={`#cite-${idx}`}
            className={
              hoveredIdx === idx
                ? "tutor-view__pill tutor-view__pill--hover"
                : "tutor-view__pill"
            }
            onMouseEnter={() => setHovered(idx)}
            onMouseLeave={() => setHovered(null)}
            onClick={(e) => {
              // Robustly open + scroll the Sources panel even when the hash is
              // already #cite-N (no hashchange fires) — the hyperlink alone was
              // not connecting the marker to the sources field.
              if (onCite) {
                e.preventDefault();
                onCite(idx);
              }
            }}
            title={cite ? formatApa(cite) : `Citation ${idx}`}
          >
            [{idx}]
          </a>,
        );
      }
      i += m[0].length;
      continue;
    }
    if (ch === "$" && dollarsBalanced) {
      const end = text.indexOf("$", i + 1);
      if (end !== -1) {
        const inner = text.slice(i + 1, end);
        // Skip prose stuffed into $…$ (model error) — render as text, not math.
        const proseWords = (inner.match(/\b[a-zA-Z]{2,}\b/g) || []).length;
        if (proseWords < 3) {
          out.push(<MathInline key={key++} tex={inner} />);
          i = end + 1;
          continue;
        }
      }
    }
    // LaTeX-style inline math: ``\( ... \)``
    if (ch === "\\" && text[i + 1] === "(") {
      const end = text.indexOf("\\)", i + 2);
      if (end !== -1) {
        out.push(<MathInline key={key++} tex={text.slice(i + 2, end)} />);
        i = end + 2;
        continue;
      }
    }
    // Bare-latex auto-wrap: backslash + recognised latex command name,
    // optionally followed by balanced ``{...}`` groups. Whitelist prevents
    // wrapping arbitrary backslash-prose like Windows paths.
    if (ch === "\\" && /[a-zA-Z]/.test(text[i + 1] || "")) {
      let j = i + 1;
      while (j < text.length && /[a-zA-Z]/.test(text[j])) j++;
      const cmd = text.slice(i + 1, j);
      if (!LATEX_COMMANDS.has(cmd)) {
        // Not a known command — treat backslash as plain text and resume.
        out.push(<React.Fragment key={key++}>{text.slice(i, j)}</React.Fragment>);
        i = j;
        continue;
      }
      // Consume any chained ``{...}`` argument groups.
      while (j < text.length && text[j] === "{") {
        let depth = 1;
        j++;
        while (j < text.length && depth > 0) {
          if (text[j] === "{") depth++;
          else if (text[j] === "}") depth--;
          j++;
        }
      }
      // Optional subscript/superscript like ``_i`` or ``^2`` or ``_{...}``.
      while (j < text.length && (text[j] === "_" || text[j] === "^")) {
        j++;
        if (text[j] === "{") {
          let depth = 1;
          j++;
          while (j < text.length && depth > 0) {
            if (text[j] === "{") depth++;
            else if (text[j] === "}") depth--;
            j++;
          }
        } else if (j < text.length && /[a-zA-Z0-9]/.test(text[j])) {
          j++;
        }
      }
      const tex = text.slice(i, j);
      out.push(<MathInline key={key++} tex={tex} />);
      i = j;
      continue;
    }
    if (ch === "*" && text[i + 1] === "*") {
      const end = text.indexOf("**", i + 2);
      if (end !== -1) {
        out.push(
          <strong key={key++} className="tutor-view__strong">
            {text.slice(i + 2, end)}
          </strong>,
        );
        i = end + 2;
        continue;
      }
    }
    // Single-asterisk italic: ``*text*`` (no nested ``*`` or newline).
    // Checked after ``**`` so bold wins; unmatched ``*`` falls through to plain text.
    if (ch === "*") {
      const emMatch = text.slice(i).match(/^\*([^*\n]+)\*/);
      if (emMatch) {
        out.push(
          <em key={key++} className="tutor-view__em">
            {emMatch[1]}
          </em>,
        );
        i += emMatch[0].length;
        continue;
      }
    }
    // Plain run until next special char
    let j = i + 1;
    while (
      j < text.length &&
      text[j] !== "[" &&
      text[j] !== "$" &&
      text[j] !== "\\" &&
      text[j] !== "*"
    ) {
      j++;
    }
    out.push(<React.Fragment key={key++}>{text.slice(i, j)}</React.Fragment>);
    i = j;
  }

  return out;
}

function formatApa(c: TutorCitation): string {
  const parts: string[] = [];
  if (c.authors_short) {
    parts.push(c.year != null ? `${c.authors_short} (${c.year})` : c.authors_short);
  }
  if (c.book_name) parts.push(`*${c.book_name}*`);
  const locParts: string[] = [];
  if (c.chapter) locParts.push(c.chapter);
  if (c.section) locParts.push(`§${c.section}`);
  if (locParts.length) parts.push(locParts.join(" "));
  if (c.page_from != null) {
    parts.push(
      c.page_to && c.page_to !== c.page_from
        ? `pp. ${c.page_from}–${c.page_to}`
        : `p. ${c.page_from}`,
    );
  }
  return parts.join(", ");
}
