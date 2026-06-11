"""Extension mode — deterministic async pipeline: storyteller → editor → miner
→ researcher → curiosity_writer → citation_binder → judge.  Deepagents core
has been removed; all orchestration is pure-code asyncio.

Chinese-wall: imports ONLY src.core.* and shared src.services.chat.* infra
(schemas, retrieval, books, llm.router, _scope). NEVER imports deep_tutor*,
qa*, ow_* — extension is hard-isolated from tutor/qa.
"""
