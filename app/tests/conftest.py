"""
Test-session environment. This runs BEFORE the application's Settings are
first imported (pytest loads a parent conftest before anything beneath it),
and real environment variables outrank .env — so the suite is deterministic
whatever is in a developer's local .env:

* models: a tiny offline tokenizer stands in for BAAI/bge, so the real
  HuggingFaceTokenizer + Docling HybridChunker code path runs with no
  download; embeddings use the stub backend (semantic quality can't be
  tested without the real model).
* storage: uploads go to a throwaway temp dir, not ./data/uploads.
* limits: rate limits are raised so many tests can register/upload from the
  same client IP; the upload cap is 1 MB so the 413 path is cheap to test.
"""
import os
import tempfile
from pathlib import Path

from app.tests.helpers.tiny_models import write_tiny_tokenizer

_root = Path(tempfile.mkdtemp(prefix="rag-tests-"))
write_tiny_tokenizer(_root / "models" / "test--tiny-tokenizer")

os.environ.update(
    {
        "MODELS_DIR": str(_root / "models"),
        "LOCAL_STORAGE_DIR": str(_root / "uploads"),
        "RAG_PARSER_BACKEND": "docling",
        "RAG_DOCLING_LOCAL_MODELS_ONLY": "true",
        "RAG_CHUNKER_BACKEND": "docling",
        "RAG_CHUNKER_TOKENIZER": "huggingface",
        "RAG_CHUNKER_TOKENIZER_MODEL": "test/tiny-tokenizer",
        "RAG_CHUNKER_MAX_TOKENS": "500",
        "RAG_CHUNKER_MERGE_PEERS": "true",
        "RAG_EMBEDDING_BACKEND": "stub",
        "RAG_PICTURE_DESCRIPTION_ENABLED": "false",
        "RAG_MAX_UPLOAD_MB": "1",
        "RATE_LIMIT_DEFAULT": "10000/minute",
        "RATE_LIMIT_LOGIN": "10000/minute",
        "RATE_LIMIT_REGISTER": "10000/minute",
        "RATE_LIMIT_REFRESH": "10000/minute",
        "RATE_LIMIT_LOGOUT": "10000/minute",
        "RATE_LIMIT_UPLOAD": "10000/minute",
    }
)
