"""Services — DB consumers exposing user-facing features.

Chinese-wall rule:
- Each service (services/<name>/) imports only from core/.
- Services NEVER import from each other.
- Services NEVER import from tasks (ingestion/).
- Add a new service as services/<name>/ with its own __init__.py.
"""
