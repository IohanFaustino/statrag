"""Extension mode — agentic core (deepagents) + deterministic runner.

Chinese-wall: imports ONLY src.core.* and shared src.services.chat.* infra
(schemas, retrieval, books, llm.router, _scope). NEVER imports deep_tutor*,
qa*, ow_* — extension is hard-isolated from tutor/qa.
"""
