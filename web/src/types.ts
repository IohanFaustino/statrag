// Mirrors src/services/chat/schemas.py — keep in sync.

export type ModeId = "tutor" | "qa" | "facilitate" | "resume" | "extension";

export type ProviderId = "openai" | "deepseek" | "groq" | "google" | "alibaba";

export interface Book {
  id: string;
  title: string;
  subtitle: string;
  short: string;
  authors: string;
  authorsShort: string;
  edition: string;
  chunks: number;
  figures: number;
  chapters: number;
  color: string;
  cover: string;
  description: string;
  collection: string;
  image_collection: string;
  field: string;
  theme: string;
  selected: boolean;
  indexed: boolean;
}

export interface HighlightRange { start: number; end: number; reason?: string }

export interface Source {
  rank: number;
  book: string;
  chapter: string;
  section: string;
  title: string;
  excerpt: string;
  score: number;
  page?: number;
  chunkId: string;
  embedding: string;
  chunk: string;
  highlights: HighlightRange[];
}

export interface Figure {
  ref: string;
  book: string;
  chapter: string;
  caption: string;
  chart: string;
}

export interface RetrievalMetadata {
  rewrittenQuery: string;
  embedding: string;
  retrievalMs: number;
  collections: string[];
  filter: string;
  topK: number;
  scoreThreshold: number;
  mode: string;
}

export interface Model {
  id: string; name: string; tagline: string;
  cost: string; speed: string; ctx: string;
  recommended?: boolean;
}

export interface ModelProvider {
  id: ProviderId; name: string; short: string; color: string; models: Model[];
}

export type AssistantBlock =
  | { type: "p"; text: string }
  | { type: "math"; tex: string }
  | { type: "figure"; ref: string; book: string; chapter: string; caption: string; chart: string }
  | { type: "sources"; chips: { book: string; section: string }[] };

export interface UserMessage {
  role: "user";
  id: string;
  time: string;
  timestamp: string;
  text: string;
}

export interface AssistantMessage {
  role: "assistant";
  id: string;
  time: string;
  timestamp: string;
  mode: ModeId;
  model: string;
  books: string[];
  sourceCount: number;
  latencyMs: number;
  blocks: AssistantBlock[];
  sources?: Source[];
  figures?: Figure[];
  retrievalMetadata?: RetrievalMetadata;
  structuredOutput?: { schema: string; data: unknown };
  status: "pending" | "streaming" | "complete" | "error";
  error?: { code: string; message: string };
  stopped?: boolean;
  pendingExtensionPoints?: string[];
}

export type Message = UserMessage | AssistantMessage;

// ─── Structured output types (mirror schemas/output.py) ──────────────────────

export interface Citation {
  book: string;
  chapter: string;
  section: string;
  page?: number | null;
}

export interface FigureRef {
  ref: string;
  book: string;
  chapter: string;
  caption: string;
}

// T13-E + T19: tutor v2 ships a typed TutorAnswer with per-claim citation spans.
export interface TutorCitation {
  index: number;
  chunkId?: string;
  authors_short?: string;
  year?: number | null;
  book_name?: string;
  chapter?: string;
  section?: string;
  page_from?: number | null;
  page_to?: number | null;
  quote?: string;
}
export interface TutorAnswer {
  text: string;
  sections?: string[];
  citations?: TutorCitation[];
  math_blocks?: string[];
  figures?: FigureRef[];
}

// qa mode (mirror schemas/output.py QAScope / QAAnswer)
export interface QAScope {
  target_gap: string;
  assumed_known: string[];
  answer_form: "explanation" | "definition" | "comparison" | "derivation" | "yes_no" | "list";
  wiki_terms?: string[];
}

export interface QAAnswer {
  // Legacy (single-call QA) body. Newer deepagent runs persist the answer as
  // thesis/deepening/synthesis instead; QAAnswerCard handles both shapes.
  text?: string;
  scope?: QAScope;
  // Deepagent QA fields (thesis → body → conclusion progression).
  thesis?: string;
  deepening?: string;
  synthesis?: string;
  sub_queries?: string[];
  citations?: TutorCitation[];
  math_blocks?: string[];
  grounding?: { ok?: boolean; unsupported?: string[]; confidence?: number };
}

// QAStoryAnswer — storytelling pipeline output (intro → deepening → conclusion)
// Mirror of schemas/output.py QAStoryAnswer. Citations are StoryCitation (corpus|wikipedia).
export interface QAStoryAnswer {
  intro: string;
  deepening: string;
  conclusion: string;
  scope?: QAScope;
  citations?: StoryCitation[];
  math_blocks?: string[];
  grounding?: {
    ok?: boolean;
    unsupported?: string[];
    confidence?: number;
    unbound_markers?: number;
    lints?: string[];
    corpus_weak?: boolean;
    wiki_unavailable?: boolean;
  };
}

export interface ResolvedSubtopic {
  asked: string;
  matched_h2: string;
  section_id: string;
  score: number;
}

export interface ChapterScope {
  book_slug: string;
  chapter_id: string;
  requested_subtopics: string[];
  resolution: ResolvedSubtopic[];
}

export interface ChapterBlock {
  h2_path: string;
  section_id: string;
  body: string;
  page_from: number;
  page_to: number;
}

export interface ChapterDigest {
  mode: "facilitate" | "resume";
  scope: ChapterScope;
  intro: string;
  blocks: ChapterBlock[];
  outro: string;
  citations: TutorCitation[];
  math_blocks: string[];
  grounding: { ok?: boolean; unsupported?: string[]; confidence?: number };
}

export interface ConceptProvenance {
  book_slug: string;
  book_name: string;
  authors_short: string;
  section: string;
  page_from: number;
  page_to: number;
  chunk_id: string;
  same_author: boolean;
  fallback: boolean;
}
export interface ConceptAnchor {
  id: string;
  term: string;
  kind: "concept" | "theorem" | "formula";
  explanation: string;
  provenance: ConceptProvenance;
}
export interface FacilitateBlock {
  h2_path: string;
  section_id: string;
  key_points: string[];
  body: string;
  concepts: ConceptAnchor[];
  page_from: number;
  page_to: number;
}
export interface FacilitateDigest {
  mode: "facilitate";
  scope: ChapterScope;
  intro: string;
  blocks: FacilitateBlock[];
  outro: string;
  math_blocks: string[];
  grounding: { ok?: boolean; unsupported?: string[]; confidence?: number };
}

export interface ExtensionFootnote {
  marker: string;
  body: string;
  source: string;
  kind: "corpus" | "wikipedia";
}
export interface ExtensionPoint {
  title: string;
  curated_text: string;
  footnotes: ExtensionFootnote[];
}
export interface ExtensionDigest {
  book: string;
  chapter: string;
  points: ExtensionPoint[];
  unfilled_gaps: string[];
}

export interface ClarifyCandidate {
  slug: string;
  name: string;
  authors_short: string;
  chapters: string[];
}
export interface ClarifyData {
  reason: "book_unknown" | "book_ambiguous" | "chapter_missing" | "sections_empty";
  message: string;
  candidates: ClarifyCandidate[];
  chapter_guess: string;
  sections_guess: string[];
}

export type StructuredOutputEvent =
  | { type: "structured_output"; schema: "TutorAnswer"; data: TutorAnswer }
  | { type: "structured_output"; schema: "QAAnswer"; data: QAAnswer }
  | { type: "structured_output"; schema: "QAStoryAnswer"; data: QAStoryAnswer }
  | { type: "structured_output"; schema: "ChapterDigest"; data: ChapterDigest }
  | { type: "structured_output"; schema: "FacilitateDigest"; data: FacilitateDigest }
  | { type: "structured_output"; schema: "Clarify"; data: ClarifyData }
  | { type: "structured_output"; schema: "ExtensionDigest"; data: ExtensionDigest }
  | { type: "structured_output"; schema: string; data: unknown };

// Every chat event carries a monotonic `seq` (§13) when it comes from a
// detached run; absent on the ephemeral (no-conversationId) path and on
// client-synthesized errors.
export type ChatEvent = ChatEventBody & { seq?: number };

export type ChatEventBody =
  | { type: "meta"; mode: ModeId; books: string[]; sourceCount: number; latencyMs: number; model: string }
  | { type: "token"; text: string }
  | { type: "paragraph_break" }
  | { type: "math_block"; tex: string }
  | { type: "figure"; ref: string; book: string; chapter: string; caption: string; chart: string }
  | { type: "source_chip"; book: string; section: string }
  | { type: "sources_full"; sources: Source[] }
  | { type: "figures_full"; figures: Figure[] }
  | {
      type: "figures_meta";
      status: "ok" | "no_candidates" | "all_rejected" | "error" | "disabled" | "no_sources";
      reason: string;
      candidateCount: number;
      approvedCount: number;
    }
  | { type: "retrieval_meta"; meta: RetrievalMetadata }
  | { type: "usage"; durationMs: number; promptChars: number; completionChars: number; estTokens: number }
  | { type: "done" }
  | { type: "error"; code: string; message: string }
  | { type: "clarify"; reason: ClarifyData["reason"]; message: string;
      candidates: ClarifyCandidate[]; chapter_guess: string; sections_guess: string[] }
  | { type: "stage"; stage: string; label?: string }
  | StructuredOutputEvent;

// ─── Extension v2 — StoryDigest TS types (mirror schemas/output.py) ──────────

export interface StoryCitation {
  kind: "corpus" | "wikipedia";
  label: string;
  book_slug?: string; book_name?: string; authors?: string; year?: number;
  chapter?: string; section_id?: string; pages?: string;
  title?: string; url?: string; chunk_id?: string;
}
export interface CuriosityItem { subject: string; body: string; citations: StoryCitation[]; }
export interface StoryTake { heading: string; story: string; items: CuriosityItem[]; }
export interface StoryDigest {
  book: string; chapter: string; takes: StoryTake[]; unfilled_subjects: string[];
}
