"""Robust markdown code-fence stripping.

Replaces the buggy ``raw.strip().strip("```json").strip("```")`` idiom that
appeared throughout the chat service. The ``str.strip`` argument is a
character set, not a substring — the old code only worked when the boundary
happened to consist of the characters ``{'`', 'j', 's', 'o', 'n'}``.

Provides one function: :func:`strip_fences`. Safe for all inputs (empty,
bare JSON, JSON inside fences, missing trailing fence, multiline).
"""
from __future__ import annotations

import re

# Match an opening fence on its own line: ``` or ```json (and friends)
_OPEN_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n", re.MULTILINE)
# Match a closing fence on its own line: ```
_CLOSE_FENCE_RE = re.compile(r"\n\s*```\s*$", re.MULTILINE)
# Inline single-fence form: ```{...}``` with no newlines
_INLINE_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*(.*?)\s*```\s*$", re.DOTALL)


def strip_fences(text: str) -> str:
    """Return *text* with leading + trailing markdown code fences removed.

    Args:
        text: Raw LLM output that may or may not be wrapped in ``` fences.

    Returns:
        The content between fences when present; otherwise *text* unchanged
        (whitespace stripped).

    Examples:
        >>> strip_fences("```json\\n{}\\n```")
        '{}'
        >>> strip_fences("```{}```")
        '{}'
        >>> strip_fences("{}")
        '{}'
        >>> strip_fences("```json\\n{\\\"a\\\":1}")
        '{"a":1}'
    """
    if not text:
        return text

    s = text.strip()
    inline_match = _INLINE_FENCE_RE.match(s)
    if inline_match:
        return inline_match.group(1).strip()

    s = _OPEN_FENCE_RE.sub("", s, count=1)
    s = _CLOSE_FENCE_RE.sub("", s, count=1)
    return s.strip()
