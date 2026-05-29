import type {
  AssistantMessage, Citation, TutorAnswer, Quiz, NavigationList,
  DAG, Report, StudyPlan, Roadmap, AnnotatedReading,
} from "../types";

type Structured = NonNullable<AssistantMessage["structuredOutput"]>;

function citeLine(c: Citation): string {
  const page = c.page != null ? `, p.${c.page}` : "";
  return `${c.book} · ${c.chapter} · ${c.section}${page}`;
}

const LETTERS = "ABCDEFGHIJ";

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

function quiz(d: Quiz): string {
  const blocks = d.questions.map((q, i) => {
    const opts = q.options.map((o, j) => `- ${LETTERS[j]}. ${o}`).join("\n");
    const ans = LETTERS[q.answer_idx] ?? "?";
    return [
      `${i + 1}. ${q.stem}`,
      opts,
      `**Answer:** ${ans}`,
      q.rubric ? `_${q.rubric}_` : "",
      `(${q.difficulty} · ${citeLine(q.source)})`,
    ].filter(Boolean).join("\n\n");
  });
  return blocks.join("\n\n");
}

function navigation(d: NavigationList): string {
  const rows = d.results.map(
    (r) => `| ${r.book} | ${r.chapter} | ${r.section} | ${r.title} | ${r.score.toFixed(2)} |`,
  );
  return [
    "| Book | Chapter | Section | Title | Score |",
    "|---|---|---|---|---|",
    ...rows,
  ].join("\n");
}

function dag(d: DAG): string {
  const nodes = d.nodes.map((n) => `- \`${n.id}\` ${n.label}`).join("\n");
  const edges = d.edges.map((e) => `- ${e.from_id} → ${e.to_id} (${e.weight})`).join("\n");
  const parts = [`### Nodes\n\n${nodes}`, `### Edges\n\n${edges}`];
  if (d.cycles_broken.length) parts.push(`### Cycles broken\n\n${d.cycles_broken.join(", ")}`);
  return parts.join("\n\n");
}

function report(d: Report): string {
  const claims = d.claims.map((c) => {
    const ev = c.evidence.map((e) => `  - ${citeLine(e)}`).join("\n");
    return `- **${c.stance}** (${c.confidence}): ${c.claim}${ev ? "\n" + ev : ""}`;
  });
  const parts = [`### Claims\n\n${claims.join("\n")}`, `### Synthesis\n\n${d.synthesis}`];
  if (d.coverage_gaps.length) parts.push(`### Coverage gaps\n\n${d.coverage_gaps.map((g) => `- ${g}`).join("\n")}`);
  return parts.join("\n\n");
}

function studyPlan(d: StudyPlan): string {
  const rows = d.weeks.map((w) => {
    const secs = w.sections.map(citeLine).join("; ");
    return `| ${w.week} | ${secs} | ${w.hours_est} |`;
  });
  const table = ["| Week | Sections | Hours |", "|---|---|---|", ...rows].join("\n");
  const parts = [`**Goal:** ${d.goal}`, table];
  if (d.coverage_gaps.length) parts.push(`**Coverage gaps:** ${d.coverage_gaps.join(", ")}`);
  return parts.join("\n\n");
}

function roadmap(d: Roadmap): string {
  const scenes = d.scenes.map((s) => {
    return [
      `### Scene ${s.id}: ${s.title}`,
      `- Concept: ${s.concept}`,
      `- Visual: ${s.suggested_visual}`,
      `- Duration: ${s.duration_hint}`,
      s.figure ? `- Figure: ${s.figure}` : "",
      `- Source: ${citeLine(s.source)}`,
    ].filter(Boolean).join("\n");
  });
  return [`**Topic:** ${d.topic} (${d.duration_total_min} min)`, ...scenes].join("\n\n");
}

function annotated(d: AnnotatedReading): string {
  return d.annotations
    .map((a) => `- **${a.term}** — ${a.definition}${a.source ? ` (${citeLine(a.source)})` : ""}`)
    .join("\n");
}

export function structuredToMarkdown(structured: Structured): string {
  const { schema, data } = structured;
  switch (schema) {
    case "TutorAnswer": return tutor(data as TutorAnswer);
    case "Quiz": return quiz(data as Quiz);
    case "NavigationList": return navigation(data as NavigationList);
    case "DAG": return dag(data as DAG);
    case "Report": return report(data as Report);
    case "StudyPlan": return studyPlan(data as StudyPlan);
    case "Roadmap": return roadmap(data as Roadmap);
    case "AnnotatedReading": return annotated(data as AnnotatedReading);
    default:
      return "```json\n" + JSON.stringify(data, null, 2) + "\n```";
  }
}
