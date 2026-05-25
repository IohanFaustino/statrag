"""Schema-repair prompt builder (ADR-005).

Called by the orchestrator when Pydantic validation fails after the first LLM
response.  The repair prompt is sent as a second single-turn call; on second
failure the orchestrator emits a partial ``error`` SSE event and continues.

Chinese-wall: no src.* imports — pure stdlib.
"""
from __future__ import annotations


def build_repair_prompt(
    error: str,
    schema_json: str,
    original_output: str,
) -> str:
    """Return a repair instruction prompt for the LLM.

    Args:
        error: The Pydantic ``ValidationError`` message (or repr).
        schema_json: JSON Schema string produced by
            ``Model.model_json_schema()`` (serialized as JSON).
        original_output: The raw assistant text that failed validation.

    Returns:
        A single user-turn string instructing the LLM to emit corrected JSON.
    """
    return (
        "Your previous response did not match the required schema. "
        "Repair it and emit ONLY valid JSON.\n\n"
        f"Schema (JSON Schema):\n{schema_json}\n\n"
        f"Validation error:\n{error}\n\n"
        f"Original output:\n{original_output}\n\n"
        "Return ONLY valid JSON conforming to the schema. No prose."
    )
