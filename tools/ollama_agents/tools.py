"""Agent tools — the primitives an Ollama agent uses to act on a workspace.

Mirrors what a Claude subagent gets: read_file, write_file, edit_file, run.
Every path is confined to the workspace root (no escaping via ``..`` / abs path).
``TOOL_SCHEMAS`` are the native function-calling schemas handed to the model.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# ponytail: 4 tools cover the implementer loop. Add more only when a task needs it.
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a UTF-8 text file in the workspace and return its contents.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "workspace-relative path"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a file with the given full content.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "edit_file",
        "description": "Replace the first exact occurrence of 'old' with 'new' in a file. 'old' must appear exactly once.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}},
            "required": ["path", "old", "new"]}}},
    {"type": "function", "function": {
        "name": "run",
        "description": "Run a shell command from the workspace root and return combined stdout+stderr and exit code.",
        "parameters": {"type": "object", "properties": {
            "cmd": {"type": "string"}},
            "required": ["cmd"]}}},
]


def _resolve(root: Path, rel: str) -> Path:
    """Resolve rel under root; raise if it escapes the workspace."""
    p = (root / rel).resolve()
    root = root.resolve()
    if p != root and root not in p.parents:
        raise ValueError(f"path escapes workspace: {rel}")
    return p


def read_file(root: Path, path: str) -> str:
    return _resolve(root, path).read_text(encoding="utf-8")


def write_file(root: Path, path: str, content: str) -> str:
    p = _resolve(root, path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {path}"


def edit_file(root: Path, path: str, old: str, new: str) -> str:
    p = _resolve(root, path)
    text = p.read_text(encoding="utf-8")
    n = text.count(old)
    if n == 0:
        raise ValueError(f"'old' not found in {path}")
    if n > 1:
        raise ValueError(f"'old' found {n} times in {path}; must be unique")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return f"edited {path}"


def run(root: Path, cmd: str, timeout: int = 600) -> str:
    r = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True,
                       text=True, timeout=timeout)
    out = (r.stdout or "") + (r.stderr or "")
    return f"[exit {r.returncode}]\n{out[-6000:]}"  # tail-cap so transcript stays bounded


def dispatch(name: str, args: dict, root: Path) -> str:
    """Execute a tool call by name; return a string result (errors as text so the
    agent can recover rather than the loop crashing)."""
    fns = {"read_file": read_file, "write_file": write_file,
           "edit_file": edit_file, "run": run}
    fn = fns.get(name)
    if fn is None:
        return f"ERROR: unknown tool '{name}'"
    try:
        return fn(root, **args)
    except Exception as e:  # ponytail: surface tool errors to the model, don't crash the loop
        return f"ERROR: {type(e).__name__}: {e}"
