// Mirrors src/services/chat/schemas.py — keep in sync.

export type ModeId =
  | "tutor" | "compare" | "figures" | "quiz" | "navigate"
  | "prereqs" | "annotate" | "research" | "math" | "path" | "roadmap";

export type ProviderId = "openai" | "deepseek" | "groq";

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

export interface Question {
  stem: string;
  options: string[];
  answer_idx: number;
  rubric: string;
  source: Citation;
  difficulty: "easy" | "medium" | "hard";
}
export interface Quiz { questions: Question[] }

export interface NavResult { book: string; chapter: string; section: string; title: string; score: number; page: number | null }
export interface NavigationList { results: NavResult[] }

export interface ConceptNode { id: string; label: string; source: Citation | null }
export interface ConceptEdge { from_id: string; to_id: string; weight: number }
export interface DAG { nodes: ConceptNode[]; edges: ConceptEdge[]; cycles_broken: string[] }

export interface Annotation { term: string; definition: string; source: Citation | null; position: [number, number] }
export interface AnnotatedReading { annotations: Annotation[] }

export interface StanceClaim { claim: string; stance: "SUPPORTS" | "CONTRADICTS" | "BACKGROUND"; evidence: Citation[]; confidence: number }
export interface Report { claims: StanceClaim[]; synthesis: string; coverage_gaps: string[] }

export interface StudyWeek { week: number; sections: Citation[]; hours_est: number }
export interface StudyPlan { goal: string; weeks: StudyWeek[]; coverage_gaps: string[]; replanned_from_version: number }

export interface Scene { id: number; title: string; concept: string; source: Citation; suggested_visual: string; duration_hint: string; figure: string | null }
export interface Roadmap { topic: string; scenes: Scene[]; duration_total_min: number }

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

export type StructuredOutputEvent =
  | { type: "structured_output"; schema: "TutorAnswer"; data: TutorAnswer }
  | { type: "structured_output"; schema: "Quiz"; data: Quiz }
  | { type: "structured_output"; schema: "NavigationList"; data: NavigationList }
  | { type: "structured_output"; schema: "DAG"; data: DAG }
  | { type: "structured_output"; schema: "AnnotatedReading"; data: AnnotatedReading }
  | { type: "structured_output"; schema: "Report"; data: Report }
  | { type: "structured_output"; schema: "StudyPlan"; data: StudyPlan }
  | { type: "structured_output"; schema: "Roadmap"; data: Roadmap }
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
  | StructuredOutputEvent;
