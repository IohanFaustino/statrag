# Mode 5 — `navigate`

> **v2.** Pure ranked location list. Nano model + `retrieve` tool + native
> `response_format=NavigationList`. No prose answer — schema enforces
> structure.

---

## Spec

| Field | Value |
|-------|-------|
| `id` / `icon` | `navigate` · `map-pin` |
| `arch` | `single` |
| Runner | `langchain.agents.create_agent` |
| Model | `nano` |
| `response_format` | `NavigationList` |
| Tools | `[retrieve]` |
| Builder | `src/services/chat/mode_impls/navigate.py` |

---

## Pipeline

```mermaid
flowchart LR
    accTitle: Navigate v2 pipeline
    accDescr: Lookup request goes to nano LLM, agent calls retrieve once or twice, NavigationList JSON emitted via response_format.

    user["📝 S1<br/>lookup query"]
    agent["🤖 S2<br/>nano agent"]
    tool["🔧 S3<br/>retrieve<br/>top_k"]
    constrained["📜 S4<br/>NavigationList<br/>schema"]
    sse["📤 S5<br/>structured<br/>_output"]

    user --> agent
    agent --> tool
    tool --> agent
    agent --> constrained
    constrained --> sse

    classDef input fill:#1e3a8a,stroke:#3b82f6,color:#fff
    classDef llm fill:#854d0e,stroke:#eab308,color:#fff
    classDef tool fill:#0e7490,stroke:#06b6d4,color:#fff
    classDef schema fill:#9a3412,stroke:#f97316,color:#fff
    classDef out fill:#7f1d1d,stroke:#ef4444,color:#fff

    class user input
    class agent llm
    class tool tool
    class constrained schema
    class sse out
```

---

## Builder — `mode_impls/navigate.py`

```python
@lru_cache(maxsize=1)
def build_agent():
    return build_structured_agent(
        system_prompt=INSTRUCTIONS,
        tools=[retrieve],
        response_format=NavigationList,
    )
```

---

## Output schema

`NavigationList` (`schemas/output.py:119-135`):

```python
class NavResult(BaseModel):
    book: str
    chapter: str
    section: str
    title: str
    score: float
    page: int | None = None
    snippet: str = ""

class NavigationList(BaseModel):
    results: list[NavResult]
    expanded_terms: list[str] = []
```

---

## HyDE / query expansion

v1 used `query_expansion.expand_queries(..., flags=RetrievalFlags(hyde=True))`
upstream of retrieval. v2 leaves expansion **inside the `retrieve` tool**
(the LLM can pass already-expanded queries as multiple `retrieve` calls if
needed) — keeping the agent-loop in control of how many round-trips happen.

A Phase 2 ticket may re-introduce HyDE as an explicit `@tool hyde_expand`.

---

## Synopsis

Lightest mode. Nano model + one tool + schema-constrained list of
locations. Stateless. Used as the "where can I find X?" workflow — pair
with `tutor` for full prose answers.
