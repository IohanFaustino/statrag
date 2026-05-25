# 26 — Chinese wall enforcement

## Rule

| Layer | Folder | Rule |
|---|---|---|
| Core (system) | `src/core/` | Shared infra. Imports nothing in repo. |
| Tasks (external → DB) | `src/ingestion/` | One-off processes. Imports only `src.core.*`. |
| Services (DB → user features) | `src/services/<name>/` | Each service imports only `src.core.*` and within-service siblings. Never imports from other services or from tasks. |

## Verification

```bash
# Chat service must NOT import ingestion or other services
grep -rE "from src\.(ingestion|services\.(retrieval|eval))" src/services/chat/

# Eval service must NOT import chat
grep -rE "from src\.services\.chat" src/services/eval/

# Both should return zero matches → wall ok
```

Run after every milestone. Both currently pass.

## How chat reads ingestion artifacts without importing

`src/services/chat/books.py` reads `data/parsed/manifest.json` + `src/ingestion/books/*.yaml` AS FILESYSTEM ARTIFACTS only — never `import src.ingestion`.

```python
# books.py
from pathlib import Path
import yaml, json

YAMLS_DIR = ROOT / "src" / "ingestion" / "books"
MANIFEST_PATH = ROOT / "data" / "parsed" / "manifest.json"

# load via pathlib + yaml/json — no module import
```

## Why it matters

- Ingestion modules use langchain (heavy); chat uses openai SDK directly (light). Coupling would pull langchain into the chat service's import graph.
- Services should be independently runnable + replaceable.
- Test isolation: chat tests don't need ingestion fixtures.

## Per-service `__init__.py` documents the rule

```python
# src/services/chat/__init__.py
"""Chat service — SSE-streaming conversational layer over hybrid retrieval.

Chinese-wall rule:
- Imports only from src.core.*.
- Never imports from other services or from src.ingestion.
- Reads data/parsed/manifest.json and src/ingestion/books/*.yaml as
  filesystem artifacts only (no module import into ingestion).
"""
```

```python
# src/services/eval/__init__.py
"""Evaluation harness for the chat service.

Wall rule: imports only src.core.*. Invokes the chat service via HTTP
(not direct module import) to preserve the Chinese wall between services.
"""
```

## When the rule is enforced

- During code review of new modules (manual)
- Pre-merge gate via the grep command above
- CI could codify with a lint rule (post-v1)
