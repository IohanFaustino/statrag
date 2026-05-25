# 20 — FastAPI app + routes

## Purpose

The HTTP/SSE surface. Mounts all routers + the `/api/chat` SSE endpoint. CORS open in dev. Vite proxies `/api/*` from `:5173` to `:8765` (or `STATRAG_BACKEND_PORT` override).

## All routes

```
GET    /api/health                                  → {status: "ok"}
GET    /api/books                                   → Book[]
GET    /api/books/{slug}                            → Book | 404
POST   /api/search                                  → {sources, figures, metadata}
GET    /api/models                                  → ModelProvider[]
GET    /api/conversations                           → ConversationDigest[]
POST   /api/conversations                           → ConversationDigest (201)
GET    /api/conversations/{conv_id}                 → digest + messages
DELETE /api/conversations/{conv_id}                 → 204 (drops Qdrant conv_<id>)
GET    /api/preferences                             → dict
PATCH  /api/preferences                             → updated dict
POST   /api/chat                                    → SSE stream of ChatEvent
GET    /api/study_plans/{conv_id}                   → StudyPlan
POST   /api/study_plans/{conv_id}/replan            → new StudyPlan, version++
DELETE /api/study_plans/{conv_id}/section/{ref}     → triggers replan
```

## Key code

`src/services/chat/api.py`:

```python
app = FastAPI(title="statrag chat", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(books.router, prefix="/api")
app.include_router(retrieval.router, prefix="/api")
app.include_router(llm_router.router, prefix="/api")
app.include_router(store.router, prefix="/api")


@app.get("/api/health")
async def health(): return {"status": "ok"}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    async def event_gen():
        try:
            history = None
            if req.conversationId:
                try: history = store.get_messages(req.conversationId)
                except Exception: history = None
            async for ev in stream_chat(req, history=history):
                yield {"event": ev.get("type", "message"), "data": json.dumps(ev)}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({
                "type": "error", "code": type(e).__name__, "message": str(e),
            })}
            yield {"event": "done", "data": json.dumps({"type": "done"})}
    return EventSourceResponse(event_gen(), ping=15)


# M7 study_plans routes added directly on app:
@app.get("/api/study_plans/{conv_id}")
def api_get_study_plan(conv_id: str): ...

@app.post("/api/study_plans/{conv_id}/replan")
async def api_replan_study_plan(conv_id: str, body: _ReplanBody): ...

@app.delete("/api/study_plans/{conv_id}/section/{ref}")
async def api_delete_section(conv_id: str, ref: str): ...
```

## Run

```bash
# Direct uvicorn:
.venv/bin/python -m uvicorn src.services.chat.api:app --reload --port 8765

# Dev script (backend + frontend together):
./scripts/dev.sh
# STATRAG_BACKEND_PORT=8800 ./scripts/dev.sh   # custom port
```

## SSE headers

`sse-starlette.EventSourceResponse` sets:
- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`
- `Connection: keep-alive`
- `X-Accel-Buffering: no` (defeats nginx buffering)

Vite's proxy config (`web/vite.config.ts`) also sets these for relayed responses.

## Tests

`test_sse.py::TestFastAPIEndpoints` — 3 tests using `TestClient`:
- `/api/health` → 200
- `/api/models` → non-empty list
- `/api/books` → list

End-to-end SSE event ordering tested separately via `TestStreamChat` (11 tests).

## OpenAPI

Visit `http://localhost:8765/docs` for the interactive Swagger UI. All schemas auto-generated from Pydantic models.
