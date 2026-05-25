# P2 — Foundation Models (Polzer)

**Prompt template design**, language model selection per task, generation via OpenAI/Gemini/Anthropic APIs, **local via Ollama**.

**Relevance**: high.
- Prompt template recipes = ready building blocks for our `prompts/` dir.
- Model selection per task → multi-provider routing.

**Take**: structured prompt template per mode (system + few-shot + schema). Add Ollama path as offline fallback in `llm/router.py`.
