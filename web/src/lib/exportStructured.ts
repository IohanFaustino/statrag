import type {
  AssistantMessage, TutorAnswer, QAAnswer, FacilitateDigest, ChapterDigest, TutorCitation,
} from "../types";

type Structured = NonNullable<AssistantMessage["structuredOutput"]>;

// Shared numbered-citations section. Same format across tutor / qa / chapter.
// Returns "" when there are no citations.
function citationsSection(citations: TutorCitation[] | undefined): string {
  if (!citations || !citations.length) return "";
  const lines = citations.map((c) => {
    const who = [c.authors_short, c.year].filter(Boolean).join(" ");
    const loc = [c.book_name, c.chapter, c.section].filter(Boolean).join(" · ");
    const quote = c.quote ? ` — "${c.quote}"` : "";
    return `${c.index}. ${[who, loc].filter(Boolean).join(" — ")}${quote}`;
  });
  return "### Citations\n\n" + lines.join("\n");
}

// Shared display-math section ($$…$$ blocks). Returns "" when empty.
function mathSection(mathBlocks: string[] | undefined): string {
  if (!mathBlocks || !mathBlocks.length) return "";
  return "### Math\n\n" + mathBlocks.map((tex) => `$$\n${tex}\n$$`).join("\n\n");
}

function tutor(d: TutorAnswer): string {
  const parts: string[] = [d.text.trim()];
  const cites = citationsSection(d.citations);
  if (cites) parts.push(cites);
  if (d.figures && d.figures.length) {
    const figs = d.figures.map((f) => `- **${f.ref}** ${f.caption} (${f.book} · ${f.chapter})`);
    parts.push("### Figures\n\n" + figs.join("\n"));
  }
  return parts.join("\n\n");
}

function qa(d: QAAnswer): string {
  // Support both legacy (text) and deepagent (thesis/deepening/synthesis) shapes.
  const bodyText = typeof d.text === "string" && d.text.trim()
    ? d.text.trim()
    : [d.thesis, d.deepening, d.synthesis]
        .filter((s): s is string => typeof s === "string" && s.trim().length > 0)
        .join("\n\n");
  const parts: string[] = [bodyText];
  const scope = d.scope;
  if (scope) {
    const scopeParts = [`**Scope:** ${scope.target_gap}`];
    if (scope.assumed_known && scope.assumed_known.length) {
      scopeParts.push(`assuming you know: ${scope.assumed_known.join(", ")}`);
    }
    parts.push(scopeParts.join(" · "));
  }
  const cites = citationsSection(d.citations);
  if (cites) parts.push(cites);
  const math = mathSection(d.math_blocks);
  if (math) parts.push(math);
  return parts.join("\n\n");
}

// Resume mode (and any ChapterDigest): intro → per-section heading+body (in list
// order = chapter order) → outro → citations → math. Plain markdown, no json.
function chapter(d: ChapterDigest): string {
  const parts: string[] = [];
  if (d.intro && d.intro.trim()) parts.push(d.intro.trim());
  for (const block of d.blocks) {
    const blockParts = [`## ${block.h2_path}`];
    if (block.body && block.body.trim()) blockParts.push(block.body.trim());
    parts.push(blockParts.join("\n\n"));
  }
  if (d.outro && d.outro.trim()) parts.push(d.outro.trim());
  const cites = citationsSection(d.citations);
  if (cites) parts.push(cites);
  const math = mathSection(d.math_blocks);
  if (math) parts.push(math);
  return parts.join("\n\n");
}

function facilitate(d: FacilitateDigest): string {
  const parts: string[] = [];
  if (d.intro && d.intro.trim()) parts.push(d.intro.trim());
  const footnoteDefs: string[] = [];
  for (let bi = 0; bi < d.blocks.length; bi++) {
    const block = d.blocks[bi];
    const blockParts: string[] = [`## ${block.h2_path}`];
    if (block.key_points && block.key_points.length) {
      blockParts.push(block.key_points.map((kp) => `- ${kp}`).join("\n"));
    }
    const body = block.body.replace(/\[\[(c\d+)\]\]/g, `[^b${bi}$1]`);
    blockParts.push(body);
    parts.push(blockParts.join("\n\n"));
    for (const concept of block.concepts) {
      const prov = concept.provenance;
      const def = `[^b${bi}${concept.id}]: ${concept.term} — ${concept.explanation} (${prov.authors_short}, ${prov.section}, p.${prov.page_from})`;
      footnoteDefs.push(def);
    }
  }
  if (d.outro && d.outro.trim()) parts.push(d.outro.trim());
  if (footnoteDefs.length) parts.push(footnoteDefs.join("\n"));
  return parts.join("\n\n");
}

export function structuredToMarkdown(structured: Structured): string {
  const { schema, data } = structured;
  switch (schema) {
    case "TutorAnswer": return tutor(data as TutorAnswer);
    case "QAAnswer": return qa(data as QAAnswer);
    case "ChapterDigest": return chapter(data as ChapterDigest);
    case "FacilitateDigest": return facilitate(data as FacilitateDigest);
    default:
      return "```json\n" + JSON.stringify(data, null, 2) + "\n```";
  }
}
