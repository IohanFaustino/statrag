# A3 — LLMs as Powerful AI Engine

Scaling law, emergent properties, context length, MoE, instruction tuning, LoRA, RLHF, SLMs, multimodal, hallucinations + ethics, **prompt engineering / ICL / demonstrations**.

**Relevance to chat RAG**: high.
- Prompt engineering + ICL → system prompt design + few-shot demos for each mode.
- Hallucinations → forces mandatory citation + groundedness checks.
- Context length awareness → budget rules.
- SLM section → use small models for routing/classification, big for synthesis.

**Take**: mine prompts + ICL patterns for tutor/quiz/navigator. Use SLM-routing argument to pick gpt-5.4-nano default + escalation rule to deepseek-v4-pro.
