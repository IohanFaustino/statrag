"""Centralized configuration loaded from environment / .env.

All pipeline modules import from here so changing a setting (model, weights,
paths) requires no code edits — only `.env`.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT: Path = Path(__file__).resolve().parent.parent.parent
DATA_DIR: Path = ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
BM25_DIR: Path = DATA_DIR / "bm25"
BM25_PICKLE: Path = BM25_DIR / "corpus.pkl"


class Settings(BaseSettings):
    """Runtime configuration. Values come from `.env` or env vars."""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    deepseek_api_key: str = Field("", alias="DEEPSEEK_API_KEY")
    qdrant_host: str = Field("localhost", alias="QDRANT_HOST")
    qdrant_port: int = Field(6333, alias="QDRANT_PORT")
    qdrant_api_key: str = Field("", alias="QDRANT_API_KEY")
    qdrant_collection_text: str = Field("introduction_textbooks", alias="QDRANT_COLLECTION_TEXT")
    qdrant_collection_images: str = Field("introduction_images", alias="QDRANT_COLLECTION_IMAGES")
    # legacy alias (kept until full removal):
    chroma_collection: str = Field("introduction_textbooks", alias="CHROMA_COLLECTION")
    embedding_model: str = Field("text-embedding-3-large", alias="EMBEDDING_MODEL")
    llm_model: str = Field("gpt-5.4-nano-2026-03-17", alias="LLM_MODEL")
    openai_model_nano: str = Field("gpt-5.4-nano-2026-03-17", alias="OPENAI_MODEL_NANO")
    openai_model_full: str = Field("gpt-5.4-2026-03-05", alias="OPENAI_MODEL_FULL")
    deepseek_model: str = Field("deepseek-v4-pro", alias="DEEPSEEK_MODEL")
    deepseek_base_url: str = Field("https://api.deepseek.com/v1", alias="DEEPSEEK_BASE_URL")
    groq_api_key: str = Field("", alias="GROQ_API_KEY")
    groq_base_url: str = Field("https://api.groq.com/openai/v1", alias="GROQ_BASE_URL")
    groq_default_model: str = Field(
        "meta-llama/llama-4-scout-17b-16e-instruct", alias="GROQ_DEFAULT_MODEL"
    )
    default_provider: str = Field("openai", alias="DEFAULT_PROVIDER")
    dense_weight: float = Field(0.6, alias="DENSE_WEIGHT")
    sparse_weight: float = Field(0.4, alias="SPARSE_WEIGHT")
    top_k: int = Field(5, alias="TOP_K")
    reranker_model: str = Field("BAAI/bge-reranker-v2-m3", alias="RERANKER_MODEL")
    rerank_top_k_in: int = Field(50, alias="RERANK_TOP_K_IN")
    rerank_top_n_out: int = Field(10, alias="RERANK_TOP_N_OUT")
    chunk_size: int = 800
    chunk_overlap: int = 120
    parent_max_chars: int = 25_000

    # --- v2 chat service settings (ADR-006) ---
    use_v2_modes: list[str] = Field(
        # T12 default: v2 (LangChain + LangGraph) handles all modes; set to
        # an explicit list (or empty) to roll back specific modes to the v1
        # orchestrator. ``["*"]`` means "every mode v2".
        default_factory=lambda: ["*"],
        alias="USE_V2_MODES",
        description="Comma-separated list of mode IDs migrated to LangChain+LangGraph v2. "
        "Modes not in this list fall back to the v1 orchestrator. "
        "Default: ['*'] (all modes on v2).",
    )
    checkpointer_db: str = Field(
        "data/checkpoints.db",
        alias="CHECKPOINTER_DB",
        description="SQLite path for LangGraph checkpointer (chat history + thread state).",
    )
    langsmith_disabled: bool = Field(
        False,
        alias="LANGSMITH_DISABLED",
        description="Opt-out flag for LangSmith auto-tracing. Tracing is on by default in dev.",
    )

    def parsed_use_v2_modes(self) -> list[str]:
        """Return v2 modes as a list, parsing comma-separated env strings."""
        if isinstance(self.use_v2_modes, str):
            return [m.strip() for m in self.use_v2_modes.split(",") if m.strip()]
        return list(self.use_v2_modes)


settings = Settings()  # type: ignore[call-arg]
