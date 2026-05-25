"""Evaluation harness for the chat service.

Wall rule: imports only `src.core.*`. Invokes the chat service via HTTP
(not direct module import) to preserve the Chinese wall between services.
"""
