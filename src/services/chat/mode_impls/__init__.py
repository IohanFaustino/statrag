"""v2 single-agent modes built on LangChain `create_agent`.

Named `mode_impls` (not `modes`) because the v1 `ModeSpec` registry lives in
the sibling `modes.py` module and we keep both during the staged rollout.

One module per mode. Each module exposes a `build_agent()` factory that
returns a compiled LangGraph agent. The factory is invoked once per process
and the result is cached in `router.MODE_REGISTRY`.

Chinese-wall: imports only from `src.core.*` and sibling `src.services.chat.*`
modules. Must never import from `src.ingestion` or other services.

ADR-006: this package is the v2 surface; v1 lives in `src/services/chat/orchestrator.py`
until T12 deletes it.
"""
