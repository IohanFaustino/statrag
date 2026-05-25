"""Ingestion task — external-input → DB writer.

Chinese-wall rule:
- ingestion/ imports only from core/ and third-party libs.
- No imports from services/.
- Other tasks/services never import from ingestion/.
"""
