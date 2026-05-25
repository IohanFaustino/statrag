"""Core — shared system layer.

Chinese-wall rule:
- core/ depends on NOTHING in the repo (only third-party libs).
- ingestion/ and services/ may import from src.core.
- core never imports from ingestion or services.
"""
