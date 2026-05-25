# Mode 8 — `roadmap`

> **v2.** Video production brief. `pro` model + `retrieve` tool +
> `response_format=Roadmap`. Stateless; ideal for batch generation.

---

## Spec

| Field | Value |
|-------|-------|
| `id` / `icon` | `roadmap` · `film` |
| `arch` | `single` |
| Runner | `langchain.agents.create_agent` |
| Model | `full` |
| `response_format` | `Roadmap` |
| Tools | `[retrieve]` |
| Builder | `src/services/chat/mode_impls/roadmap.py` |

---

## Pipeline

```mermaid
flowchart LR
    accTitle: Roadmap v2 pipeline
    accDescr: User topic + audience hint → pro LLM agent calls retrieve repeatedly to gather scene material → emits Roadmap JSON with ordered scenes.

    user["📝 S1<br/>topic + audience"]
    agent["🤖 S2<br/>pro agent"]
    retr["🔧 S3<br/>retrieve ×N<br/>broad coverage"]
    schema["📜 S4<br/>Roadmap<br/>response_format"]
    sse["📤 S5<br/>structured<br/>_output"]

    user --> agent
    agent --> retr
    retr --> agent
    agent --> schema
    schema --> sse

    classDef input fill:#1e3a8a,stroke:#3b82f6,color:#fff
    classDef llm fill:#854d0e,stroke:#eab308,color:#fff
    classDef tool fill:#0e7490,stroke:#06b6d4,color:#fff
    classDef schema fill:#9a3412,stroke:#f97316,color:#fff
    classDef out fill:#7f1d1d,stroke:#ef4444,color:#fff

    class user input
    class agent llm
    class retr tool
    class schema schema
    class sse out
```

---

## Builder — `mode_impls/roadmap.py`

```python
@lru_cache(maxsize=1)
def build_agent():
    return build_structured_agent(
        system_prompt=INSTRUCTIONS,
        tools=[retrieve],
        response_format=Roadmap,
        model=settings.openai_model_full,
    )
```

---

## Output schema

`Roadmap` (`schemas/output.py:257-276`):

```python
class Scene(BaseModel):
    id: int
    title: str
    concept: str
    source: Citation
    suggested_visual: str
    duration_hint: str
    figure: str | None = None

class Roadmap(BaseModel):
    topic: str
    target_audience: str = ""
    total_duration_estimate: str = ""
    duration_total_min: int = 0
    scenes: list[Scene]
```

---

## Multi-query expansion

v1 had `RetrievalFlags(multi_query=3, decompose=True, rerank=True)`. v2
delegates query breadth to the LLM: instead of pre-expanding to 3 variants
upstream of retrieval, the LLM may call `retrieve` 3 times with different
phrasings inside the agent loop. `recursion_limit=10` caps the loop.

---

## Synopsis

Heaviest single-tool agent. The LLM autonomously broadens the retrieval
pool by issuing multiple `retrieve` calls before assembling the scene
list. Stateless. Good fit for content-batch workflows where the same topic
needs fresh briefs.
