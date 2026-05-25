# 37 — Conversation load fix (persistence + active title + empty state)

## Bug

Clicking an old conversation in the sidebar appeared to "start a new one":

1. The thread pane was empty even though the click hit `/api/conversations/{id}` and returned 200.
2. The topbar still read `New conversation`.
3. The sidebar highlight did move, but visually nothing else changed.

## Root causes

There were two distinct problems:

### A. New chats were never persisted as messages

`App.tsx::handleSend` did:

```ts
const conv = await createConversation({...});
if (conv?.id) setConversationId(conv.id);   // React state — async
sendMessage(text);                            // closure captures *old* state
```

`sendMessage` (in `useChat`) reads `state.conversationId` inside its `useCallback` closure. The closure was created on the previous render when `conversationId` was still `null`, so the SSE request body went out with `conversationId: null`. On the backend, `chat_event_gen` only calls `store.append_message(...)` when `req.conversationId` is set:

```python
if req.conversationId:
    store.append_message(role="user", ...)
...
if req.conversationId and assistant_text_buf:
    store.append_message(role="assistant", ...)
```

So every conversation row was created (POST `/api/conversations`), but no messages were ever written. Loading any of these old conversations returned `{messages: []}` and rendered the welcome / empty state — indistinguishable from a fresh chat.

### B. The topbar title never tracked the loaded conversation

```ts
const activeConvTitle =
  convGroups.today.find((c) => c.active)?.title ??
  convGroups.yesterday.find((c) => c.active)?.title ??
  "New conversation";
```

The `.active` flag came from the API payload and was never set after a click; sidebar highlighting uses the `activeId` prop instead. Result: the title in the topbar was permanently stuck at `New conversation`.

## Fix

### `web/src/state/chat.ts`
`sendMessage` now accepts an optional `convIdOverride` and uses it before falling back to `state.conversationId`:

```ts
const sendMessage = useCallback(
  async (text: string, convIdOverride?: string | null) => {
    ...
    const body: ChatRequestBody = {
      conversationId: convIdOverride ?? state.conversationId,
      message: text,
      ...
```

### `web/src/App.tsx::handleSend`
Captures the freshly-created id in a local variable and forwards it to `sendMessage`:

```ts
let activeConvId = conversationId;
if (!activeConvId) {
  const conv = await createConversation({...});
  if (conv?.id) {
    activeConvId = conv.id;
    setConversationId(conv.id);
  }
}
sendMessage(text, activeConvId);
```

### `web/src/App.tsx::activeConvTitle`
Looks the active title up by id across every date group:

```ts
const findConvTitle = (id) => {
  for (const g of [today, yesterday, thisWeek, earlier]) {
    const hit = g.find((c) => c.id === id);
    if (hit) return hit.title;
  }
};
const activeConvTitle =
  findConvTitle(conversationId) ??
  /* legacy fallback */ ?? "New conversation";
```

### `web/src/components/MessageThread.tsx`
Accepts a new `conversationLoaded` prop. When the thread is empty and a conversation *is* loaded, render `No messages in this conversation yet. — Send a message below to continue.` instead of the generic `What do you want to understand?` welcome. This makes it visually obvious that the click did load a conversation, even when the loaded conversation happens to be empty (which is the case for every conversation created before fix A landed).

`App.tsx` passes `conversationLoaded={!!conversationId}`.

## Verify

```bash
cd web && npx tsc --noEmit && npx vite build
docker cp web/dist/. statrag-web:/usr/share/nginx/html/
```

In the browser, click any conversation in the sidebar:

- Topbar updates from `Today / New conversation` to `Today / <conv title>`.
- Sidebar row gets the active highlight.
- Thread pane shows either the loaded messages OR the explicit "No messages in this conversation yet." state.
- Send a new message in a fresh chat: the conversation now contains both the user and assistant rows (verify via `curl http://localhost:8765/api/conversations/<id>`).

## Cleanup note

Pre-existing orphan conversations (rows with zero messages, created before fix A) are still in the SQLite store. They render correctly now (as "No messages in this conversation yet.") but are otherwise dead weight. Deleting them is out of scope for this fix; use the existing `DELETE /api/conversations/{id}` route if a sweep is desired.
