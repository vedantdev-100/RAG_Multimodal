"""
Centralized, validated application settings.

Design decision: all configuration flows through ONE pydantic-settings object.
This means misconfiguration (missing secret, bad DB url) fails at process
startup ("fail fast") instead of surfacing as a 500 error in production at
2 AM. Never read os.environ directly anywhere else in the codebase.
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "ai-platform"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    # --- Database ---
    DATABASE_URL: str

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- JWT ---
    JWT_PRIVATE_KEY_PATH: str
    JWT_PUBLIC_KEY_PATH: str
    JWT_ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Security ---
    BCRYPT_ROUNDS: int = 12
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_REGISTER: str = "3/minute"
    # /refresh is the most expensive endpoint to abuse today: it bcrypt-compares
    # the presented token against every active refresh token in the DB until it
    # finds a match (see AuthService._find_all_active_tokens — flagged in
    # FEATURES.md as a scaling limitation). Keep this tight until that's fixed.
    RATE_LIMIT_REFRESH: str = "10/minute"
    RATE_LIMIT_LOGOUT: str = "10/minute"
    # Applied to every route by default (defense in depth for anything not
    # explicitly limited above, including future RAG endpoints).
    RATE_LIMIT_DEFAULT: str = "60/minute"

    # --- Database connection pool ---
    # Hardcoded before; now tunable per-environment without a code change.
    # RAG workloads (bulk chunk inserts, similarity search under load) have a
    # different connection profile than the auth-only setup this started
    # with, and the right pool size differs between local dev, CI, and a
    # future Kubernetes deployment where multiple pods each hold a pool
    # against the same Postgres — that total (pods * pool_size) is what
    # actually matters against Postgres's own max_connections.
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30  # seconds to wait for a connection before raising
    DB_POOL_RECYCLE: int = 1800  # seconds; recycle connections before they go stale
    # PgBouncer note: if a pooler is later placed in front of Postgres (common
    # once this splits into microservices — see PRODUCTION_READINESS.md), and
    # it runs in transaction pooling mode, asyncpg's server-side prepared
    # statement cache must be disabled (statement_cache_size=0) or queries
    # fail unpredictably. Not needed yet — connecting directly to Postgres.

    # --- RAG / retrieval (dynamic, not hardcoded) ---
    RAG_DEFAULT_TOP_K: int = 5
    RAG_CHUNK_SIZE: int = 512  # characters/tokens per chunk, ingestion pipeline default
    RAG_CHUNK_OVERLAP: int = 50
    # "cosine" | "l2" | "inner_product" — must match the index type created
    # in the migration (ix_chunks_embedding_cosine uses vector_cosine_ops);
    # changing this alone does not change the index, same caveat as
    # EMBEDDING_DIMENSIONS below.
    RAG_DISTANCE_METRIC: str = "cosine"
    # Weight given to vector similarity vs keyword (full-text) relevance when
    # combining both in hybrid search, via reciprocal rank fusion. 1.0 = pure
    # vector, 0.0 = pure keyword.
    RAG_HYBRID_VECTOR_WEIGHT: float = 0.5

    # --- Ingestion: storage & upload limits ---
    STORAGE_BACKEND: Literal["local"] = "local"  # "s3" once object storage is added
    LOCAL_STORAGE_DIR: str = "./data/uploads"
    RAG_MAX_UPLOAD_MB: int = 25
    # Each upload runs Docling + chunking + embedding: by far the most
    # CPU-heavy endpoint in the API, so it gets its own tight limit.
    RATE_LIMIT_UPLOAD: str = "5/minute"

    # --- Model storage ---
    # Everything downloaded by `uv run python -m app.cli.download_models`
    # lives here (project root by default; gitignored). Models are loaded
    # from these local folders only — never lazily from the HuggingFace
    # cache — so runtime never needs internet access and never hits the
    # Windows symlink-permission problem the HF cache can trigger.
    MODELS_DIR: str = "./models"

    # --- Parsing (Docling) ---
    RAG_PARSER_BACKEND: Literal["docling"] = "docling"
    # Docling's converter is CPU-heavy and not documented as thread-safe;
    # parsing runs in worker threads (never on the event loop) and this
    # caps how many run at once.
    RAG_PARSER_MAX_CONCURRENCY: int = 1
    # True: Docling loads layout/table/OCR models from MODELS_DIR/docling.
    # False: Docling auto-downloads into the HuggingFace cache on first use.
    RAG_DOCLING_LOCAL_MODELS_ONLY: bool = True
    RAG_OCR_ENABLED: bool = False  # text inside scanned pages / bitmaps
    RAG_TABLE_STRUCTURE_ENABLED: bool = True  # TableFormer: real row/column structure

    # --- Picture / chart description (optional enrichment, OFF by default) ---
    # Pictures have no text for a text embedding model to embed, so each
    # one is converted to a text description by a vision-language model;
    # that description becomes searchable chunk text. Costs extra time per
    # picture at ingestion.
    RAG_PICTURE_DESCRIPTION_ENABLED: bool = False
    # "local": run a VLM on this machine (downloaded to MODELS_DIR/docling).
    # "api": send picture images to an OpenAI-compatible endpoint. SECURITY:
    # this sends document content OFF this machine — only point it at an
    # endpoint you are allowed to send that data to.
    RAG_PICTURE_DESCRIPTION_BACKEND: Literal["local", "api"] = "local"
    RAG_PICTURE_DESCRIPTION_MODEL: str = (
        "HuggingFaceTB/SmolVLM-256M-Instruct"  # local backend
    )
    RAG_PICTURE_DESCRIPTION_PROMPT: str = (
        "Describe this image in a few sentences. If it is a chart, graph or diagram, "
        "state its type, axes, series, and the key values and trends."
    )
    # Ignore pictures smaller than this fraction of the page (logos, icons).
    RAG_PICTURE_MIN_AREA: float = 0.05
    RAG_PICTURE_DESCRIPTION_API_URL: str = (
        ""  # e.g. http://localhost:11434/v1/chat/completions
    )
    RAG_PICTURE_DESCRIPTION_API_MODEL: str = ""
    RAG_PICTURE_DESCRIPTION_API_KEY: SecretStr = SecretStr("")
    RAG_PICTURE_DESCRIPTION_TIMEOUT: int = 60

    # --- Chunking ---
    RAG_CHUNKER_BACKEND: Literal["docling", "simple"] = (
        "docling"  # docling = HybridChunker
    )
    # "huggingface": count tokens with the real tokenizer of
    # RAG_CHUNKER_TOKENIZER_MODEL (loaded from MODELS_DIR). "approx": word
    # count x 1.3, no model needed — for tests/offline use only, chunk
    # sizes are then approximate.
    RAG_CHUNKER_TOKENIZER: Literal["huggingface", "approx"] = "huggingface"
    RAG_CHUNKER_TOKENIZER_MODEL: str = (
        "BAAI/bge-base-en-v1.5"  # keep equal to RAG_EMBEDDING_MODEL
    )
    # bge-base accepts 512 tokens including [CLS]/[SEP]; leave headroom so
    # embedding never silently truncates a chunk.
    RAG_CHUNKER_MAX_TOKENS: int = 500
    # True: merge undersized neighbouring chunks that share the same headings.
    RAG_CHUNKER_MERGE_PEERS: bool = True

    # --- Embeddings ---
    RAG_EMBEDDING_BACKEND: Literal["stub", "sentence_transformers"] = (
        "sentence_transformers"
    )
    RAG_EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    RAG_EMBEDDING_DEVICE: str | None = (
        None  # None/"" = auto (cuda if available), or "cpu"/"cuda"
    )
    RAG_EMBEDDING_BATCH_SIZE: int = 32
    # NOT read by the Chunk model's Vector() column — pgvector fixes the
    # dimension at the DB column level via a migration, so changing this
    # setting alone does nothing to the schema. The embedder checks the
    # loaded model's real output size against this at startup and fails
    # loudly on a mismatch instead of pgvector rejecting inserts later.
    EMBEDDING_DIMENSIONS: int = 768  # BAAI/bge-base-en-v1.5

    @model_validator(mode="after")
    def _validate_picture_description(self) -> "Settings":
        if (
            self.RAG_PICTURE_DESCRIPTION_ENABLED
            and self.RAG_PICTURE_DESCRIPTION_BACKEND == "api"
        ):
            missing = [
                name
                for name in (
                    "RAG_PICTURE_DESCRIPTION_API_URL",
                    "RAG_PICTURE_DESCRIPTION_API_MODEL",
                )
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    f"RAG_PICTURE_DESCRIPTION_BACKEND=api requires: {', '.join(missing)}"
                )
        return self

    @property
    def jwt_private_key(self) -> str:
        return Path(self.JWT_PRIVATE_KEY_PATH).read_text()

    @property
    def jwt_public_key(self) -> str:
        return Path(self.JWT_PUBLIC_KEY_PATH).read_text()

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


        # --- Retrieval ---
    RAG_RETRIEVER_BACKEND: Literal["vector", "keyword", "hybrid"] = "hybrid"
    RAG_RETRIEVAL_CANDIDATES: int = 20  # candidates fetched per side before fusion/reranking
    RAG_RRF_K: int = 60

    # --- Reranking (optional, off by default) ---
    RAG_RERANKER_ENABLED: bool = False
    RAG_RERANKER_BACKEND: Literal["local", "api"] = "local"
    RAG_RERANKER_TOP_N: int = 5

    # "local": a cross-encoder run on this machine (downloaded like other models).
    RAG_RERANKER_MODEL: str = "BAAI/bge-reranker-base"
    RAG_RERANKER_DEVICE: str | None = None  # None/"" = auto, or "cpu"/"cuda"

    # "api": Cohere or Voyage's hosted rerank endpoint. SECURITY: this sends
    # chunk text (your document content) to an external provider.
    RAG_RERANKER_API_PROVIDER: Literal["cohere", "voyage"] = "cohere"
    RAG_RERANKER_API_KEY: SecretStr = SecretStr("")
    RAG_RERANKER_API_MODEL: str = "rerank-english-v3.0"  # cohere default; voyage e.g. "rerank-2"
    RAG_RERANKER_API_TIMEOUT: int = 30

    # --- Search endpoint ---
    RATE_LIMIT_SEARCH: str = "20/minute"

    @model_validator(mode="after")
    def _validate_reranker(self) -> "Settings":
        if self.RAG_RERANKER_ENABLED and self.RAG_RERANKER_BACKEND == "api":
            if not self.RAG_RERANKER_API_KEY.get_secret_value():
                raise ValueError("RAG_RERANKER_BACKEND=api requires RAG_RERANKER_API_KEY")
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — read once, reused everywhere via Depends()."""
    return Settings()
