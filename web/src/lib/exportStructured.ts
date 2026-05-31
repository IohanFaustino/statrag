import type { AssistantMessage, TutorAnswer, QAAnswer } from "../types";

type Structured = NonNullable<AssistantMessage["structuredOutput"]>;

function tutor(d: TutorAnswer): string {
  const parts: string[] = [d.text.trim()];
  if (d.citations && d.citations.length) {
    const lines = d.citations.map((c) => {
      const who = [c.authors_short, c.year].filter(Boolean).join(" ");
      const loc = [c.book_name, c.chapter, c.section].filter(Boolean).join(" · ");
      const quote = c.quote ? ` — "${c.quote}"` : "";
      return `${c.index}. ${[who, loc].filter(Boolean).join(" — ")}${quote}`;
    });
    parts.push("### Citations\n\n" + lines.join("\n"));
  }
  if (d.figures && d.figures.length) {
    const figs = d.figures.map((f) => `- **${f.ref}** ${f.caption} (${f.book} · ${f.chapter})`);
    parts.push("### Figures\n\n" + figs.join("\n"));
  }
  return parts.join("\n\n");
}

function qa(d: QAAnswer): string {
  const parts: string[] = [d.text.trim()];
  const scope = d.scope;
  const scopeParts = [`**Scope:** ${scope.target_gap}`];
  if (scope.assumed_known && scope.assumed_known.length) {
    scopeParts.push(`assuming you know: ${scope.assumed_known.join(", ")}`);
  }
  parts.push(scopeParts.join(" · "));
  if (d.citations && d.citations.length) {
    const lines = d.citations.map((c) => {
      const who = [c.authors_short, c.year].filter(Boolean).join(" ");
      const loc = [c.book_name, c.chapter, c.section].filter(Boolean).join(" · ");
      const quote = c.quote ? ` — "${c.quote}"` : "";
      return `${c.index}. ${[who, loc].filter(Boolean).join(" — ")}${quote}`;
    });
    parts.push("### Citations\n\n" + lines.join("\n"));
  }
  if (d.math_blocks && d.math_blocks.length) {
    const maths = d.math_blocks.map((tex) => `$$\n${tex}\n$$`);
    parts.push("### Math\n\n" + maths.join("\n\n"));
  }
  return parts.join("\n\n");
}

export function structuredToMarkdown(structured: Structured): string {
  const { schema, data } = structured;
  switch (schema) {
    case "TutorAnswer": return tutor(data as TutorAnswer);
    case "QAAnswer": return qa(data as QAAnswer);
    default:
      return "```json\n" + JSON.stringify(data, null, 2) + "\n```";
  }
}
