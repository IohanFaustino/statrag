# 27 — Config (`src/core/config.py`)

## Purpose

Single Pydantic settings class loaded once at module import. All env vars + defaults centralized. `.env` file at repo root.

## Settings reference

```python
class Settings(BaseSettings):
    # OpenAI
    openai_api_key:     str    = Field(..., alias="OPENAI_API_KEY")
    embedding_model:    str    = Field("text-embedding-3-large", alias="EMBEDDING_MODEL")
    llm_model:          str    = Field("gpt-5.4-nano-2026-03-17", alias="LLM_MODEL")
    openai_model_nano:  str    = Field("gpt-5.4-nano-2026-03-17", alias="OPENAI_MODEL_NANO")
    openai_model_full:  str    = Field("gpt-5.4-2026-03-05", alias="OPENAI_MODEL_FULL")
    # DeepSeek
    deepseek_api_key:   str    = Field("", alias="DEEPSEEK_API_KEY")
    deepseek_model:     str    = Field("deepseek-v4-pro", alias="DEEPSEEK_MODEL")
    deepseek_base_url:  str    = Field("https://api.deepseek.com/v1", alias="DEEPSEEK_BASE_URL")
    default_provider:   str    = Field("openai", alias="DEFAULT_PROVIDER")
    # Qdrant
    qdrant_host:        str    = Field("localhost", alias="QDRANT_HOST")
    qdrant_port:        int    = Field(6333, alias="QDRANT_PORT")
    qdrant_api_key:     str    = Field("", alias="QDRANT_API_KEY")
    qdrant_collection_text:   str = Field("introduction_textbooks", alias="QDRANT_COLLECTION_TEXT")
    qdrant_collection_images: str = Field("introduction_images", alias="QDRANT_COLLECTION_IMAGES")
    # Retrieval (legacy ingestion params)
    dense_weight:       float  = Field(0.6, alias="DENSE_WEIGHT")
    sparse_weight:      float  = Field(0.4, alias="SPARSE_WEIGHT")
    top_k:              int    = Field(5,   alias="TOP_K")
    chunk_size:         int    = 800
    chunk_overlap:      int    = 120
    parent_max_chars:   int    = 25_000
    # Reranker (M1)
    reranker_model:     str    = Field("BAAI/bge-reranker-v2-m3", alias="RERANKER_MODEL")
    rerank_top_k_in:    int    = Field(50, alias="RERANK_TOP_K_IN")
    rerank_top_n_out:   int    = Field(10, alias="RERANK_TOP_N_OUT")


settings = Settings()  # singleton
```

## Path constants

```python
ROOT:     Path = Path(__file__).resolve().parent.parent.parent
DATA_DIR: Path = ROOT / "data"
RAW_DIR:  Path = DATA_DIR / "raw"
BM25_DIR: Path = DATA_DIR / "bm25"
BM25_PICKLE: Path = BM25_DIR / "corpus.pkl"
```

## Env file

`.env` (symlinked to shared location):
```
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=...           # optional
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

Anything else uses defaults.

## Usage

```python
from src.core.config import settings

settings.openai_api_key           # required
settings.embedding_model           # "text-embedding-3-large"
settings.reranker_model            # "BAAI/bge-reranker-v2-m3"
```

## Trade

Single global singleton — convenient, but tests requiring different settings must monkeypatch `src.core.config.settings.<field>`. Acceptable for current scope.
