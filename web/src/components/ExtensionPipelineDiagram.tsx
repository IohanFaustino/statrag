import FlowDiagram, { type FlowNode } from "./FlowDiagram";

// Static node list for the Extension v2 deterministic async pipeline.
// Mirrors src/services/chat/agents/extension_runner.py round stages.
// Two PURE-CODE stages (researcher, citation_binder) use kind "data" — no LLM.
const EXTENSION_NODES: FlowNode[] = [
  {
    id: "scope",
    label: "Scope",
    desc: "Resolves book/chapter/sections from the user message. Stamps authoritative book and narrowed chapter label (e.g. ch07 · 7.4–7.5). Clarifies if target is ambiguous.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "fetch",
    label: "Fetch",
    desc: "Structural fetch of the scoped sections from the corpus (Qdrant scroll, book + chapter filter). No LLM.",
    kind: "data",
    defaultModel: "Qdrant scroll (book + chapter filter)",
  },
  {
    id: "storyteller",
    label: "Storyteller ×N (parallel)",
    desc: "One take per section, run in parallel. 2–4 short paragraphs with a plain-text heading; opens with a bridge from the previous take. English-pinned, follows the author's sequence.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "story_editor",
    label: "Story editor",
    desc: "Stitches all takes into one continuous voice with explicit through-line transitions. Adds no new facts; growth capped at ≤10%; preserves paragraph breaks.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "subject_miner",
    label: "Subject miner ×take (parallel)",
    desc: "Mines curiosity subjects per take using a gap taxonomy: formal-def / derivation / comparative / application / history. Produces 2–3 short search queries per subject.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "researcher",
    label: "Researcher ×subject",
    desc: "PURE CODE — no LLM. Multi-query hybrid search cross-book (excludes target book, rerank ON, score floor, deduped) + Wikipedia REST (mined queries first, title fallback). Emits Evidence{id, kind, text, meta}.",
    kind: "data",
    defaultModel: "hybrid search + Wikipedia REST",
  },
  {
    id: "curiosity_writer",
    label: "Curiosity writer ×take (parallel)",
    desc: "Writes curiosity bullets FROM evidence only; emits evidence_ids. FORBIDDEN to write citation text or invent facts. Body: 1–2 short paragraphs per subject.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
  {
    id: "citation_binder",
    label: "Citation binder",
    desc: "PURE CODE — no LLM. Maps evidence_ids → StoryCitation fields copied VERBATIM from retrieval payloads (book/authors/year/chapter/section/pages or wiki title+URL). Bullets with zero valid ids are moved to unfilled_subjects.",
    kind: "data",
    defaultModel: "evidence_ids → verbatim citation fields",
  },
  {
    id: "judge",
    label: "Judge",
    desc: "Per-take coverage check. ONE bounded retry of miner→researcher→writer for takes that failed coverage; then accepts with gaps listed in unfilled_subjects.",
    kind: "llm",
    defaultModel: "gpt-5.4-nano-2026-03-17",
  },
];

/** Read-only Extension v2 pipeline graph for the mode's (i) modal.
 *  No per-stage model dropdowns — model overrides for Extension are handled
 *  via the global model picker, not per-node.
 *  Output: StoryDigest → StoryDigestCard (timeline rail + curiosity toggles) + ZIP export.
 *  Legacy ExtensionDigest conversations render on the old card. */
export default function ExtensionPipelineDiagram() {
  return (
    <FlowDiagram
      nodes={EXTENSION_NODES}
      inputLabel="Book + chapter"
      outputLabel="StoryDigest"
      providers={[]}
      stageModels={{}}
      onStageModelChange={() => {}}
    />
  );
}
