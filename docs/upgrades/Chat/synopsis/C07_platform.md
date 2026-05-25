# C7 — Agent Platform "Nexus" (Lanham)

Nexus platform, Streamlit chat UI, **agent profiles + personas**, agent engine, actions/tools.

**Relevance**: high (profile concept) + low (Nexus).
- Profile/persona = system-prompt template per mode. Matches our mode-switch design.
- Streamlit irrelevant (we use React).

**Take**: implement `Persona` class per mode = system prompt + few-shot demos + output schema + tool list.
