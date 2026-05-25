import type { Book, ModelProvider } from "../types";

interface ConversationRaw {
  id: string;
  title: string;
  mode: string;
  updatedAt?: string;
  active?: boolean;
}

interface ConversationsResponse {
  conversations: ConversationRaw[];
  roadmaps?: { id: string; title: string; scenes: number; date: string }[];
}

interface CreateConversationBody {
  title?: string;
  mode?: string;
  model_id?: string;
  book_filter?: string[] | "ALL";
}

interface CreatedConversation {
  id: string;
  title: string;
  mode: string;
  createdAt?: string;
}

export async function fetchBooks(): Promise<Book[]> {
  const r = await fetch("/api/books");
  if (!r.ok) throw new Error(`fetchBooks: http ${r.status}`);
  return r.json() as Promise<Book[]>;
}

export async function fetchProviders(): Promise<ModelProvider[]> {
  const r = await fetch("/api/models");
  if (!r.ok) throw new Error(`fetchProviders: http ${r.status}`);
  return r.json() as Promise<ModelProvider[]>;
}

export async function fetchConversations(): Promise<ConversationsResponse> {
  const r = await fetch("/api/conversations");
  if (!r.ok) throw new Error(`fetchConversations: http ${r.status}`);
  return r.json() as Promise<ConversationsResponse>;
}

export async function createConversation(
  body: CreateConversationBody,
): Promise<CreatedConversation> {
  const r = await fetch("/api/conversations", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`createConversation: http ${r.status}`);
  return r.json() as Promise<CreatedConversation>;
}
