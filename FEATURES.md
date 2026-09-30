# FEATURES.md

Living document. Every PR that adds, changes, or removes a feature must
update this file in the same commit (see `AGENTS.md` Section 4).

Status legend: ✅ Implemented · 🚧 In Progress · 📋 Planned

---

## Auth & Identity

| Feature | Status | Notes |
|---|---|---|
| User registration (email/password) | ✅ | `POST /api/v1/auth/register`, bcrypt hashing |
| Login (JWT issuance) | ✅ | `POST /api/v1/auth/login`, RS256 access token + opaque refresh token |
| Access token verification | ✅ | Stateless, RS256, 15 min TTL, unique `jti` per token, `app/dependencies/auth.py` |
| Refresh token rotation | ✅ | Old token revoked on use, `POST /api/v1/auth/refresh` |
| Logout / token revocation | ✅ | `POST /api/v1/auth/logout` |
| Role-based access control (role field) | ✅ | `user`, `admin` — `require_role()` dependency |
| Superuser/admin creation CLI (Django `createsuperuser` equivalent) | ✅ | `uv run python -m app.cli.create_superuser` — `app/cli/create_superuser.py` |
| Scope-based authorization | ✅ | `require_scopes()` dependency, e.g. `rag:query`, `rag:ingest` |
| Rate limiting on login | ✅ | slowapi, in-memory backend (see "known limitations" below) |
| Rate limiting on register/refresh/logout + global default | ✅ | slowapi, configurable per-route via `.env`; verified with live load test |
| Refresh-token lookup by scan | ✅ (temporary) | O(n) scan in `auth_service.py`, flagged for `token_id`-indexed rewrite |
| Email verification flow | 📋 | `is_verified` field exists on `User`, no email-send flow yet |
| Password reset flow | 📋 | Not started |
| OAuth2 / social login | 📋 | Not started |
| MFA | 📋 | Not started |
| Distributed rate-limit backend (Redis) | 📋 | Needed before multi-replica production deploy |

## Platform / Infrastructure

| Feature | Status | Notes |
|---|---|---|
| Async SQLAlchemy + Postgres | ✅ | `app/db/session.py`, verified against live Postgres 16 |
| Alembic migrations | ✅ | Async-engine env.py, autogenerate wired to all models; first migration generated + applied |
| Structured JSON logging + request-ID correlation | ✅ | `app/logging/` package (`config.py`, `middleware.py`) |
| Centralized domain exceptions + HTTP mapping | ✅ | `app/exceptions/` package — `base.py` (exception types), `handlers.py` (one place mapping to status codes) |
| Shared utilities (datetime, ID gen, pagination) | ✅ | `app/utils/` package |
| Centralized fail-fast config (pydantic-settings) | ✅ | `app/core/config.py` |
| Global exception handling (no stack-trace leakage in prod) | ✅ | `app/main.py` |
| Dockerized local dev (app + Postgres + Redis) | ✅ | `docker-compose.yml` |
| uv dependency management (exact pins + lockfile) | ✅ | `pyproject.toml`, `uv.lock` |
| Supply-chain cooldown (`exclude-newer`) + no-prerelease policy | ✅ | `[tool.uv]` in `pyproject.toml` |
| CI: lint + typecheck + test + lockfile-drift check | ✅ | `.github/workflows/ci.yml` |
| Observability (metrics/tracing, e.g. OpenTelemetry) | 📋 | Not started |
| Secrets manager integration (Vault/AWS Secrets Manager) | 📋 | Currently env-file based |

## AI Capabilities (RAG only — multi-agent lives in a separate project)

| Feature | Status | Notes |
|---|---|---|
| Guardrail pipeline interface (`Guardrail`, `GuardrailPipeline`) | ✅ | `app/guardrails/base.py` — interface only |
| Prompt-injection detection | 📋 | Interface ready, implementation not started |
| PII detection/redaction | 📋 | Interface ready, implementation not started |
| Output toxicity/hallucination filtering | 📋 | Interface ready, implementation not started |
| RAG ingestion pipeline | ✅ | `app/rag/ingestion/` — `LocalFileStorage`, `DoclingParser` (layout-aware: tables, pictures, headings all extracted — not just plain text), `DoclingHybridChunker` (now calls Docling's real `HybridChunker`; earlier version built one but never used it) / `SimpleChunker`, `StubEmbeddingGenerator` / `SentenceTransformersEmbedder` (default; loads BAAI/bge-base from a local `MODELS_DIR` folder, no runtime internet access), `IngestionService` orchestrator. All swappable via `Settings` (`app/rag/ingestion/factory.py`). Verified with unit tests against real Docling + a tiny local tokenizer/embedding model; the real BAAI/bge weights and the PDF path were not exercised in this sandbox (no HuggingFace network access) — see `PRODUCTION_READINESS.md`. |
| Table extraction | ✅ | `TableItem`s kept as `modality="table"` chunks with row/column labels via Docling's `HybridChunker`; previously silently dropped |
| Picture/chart description | ✅ (optional, off by default) | `RAG_PICTURE_DESCRIPTION_ENABLED` — local VLM or OpenAI-compatible API; turns picture content into searchable text; `Document.doc_metadata` records how many pictures were and weren't described |
| Model download command | ✅ | `uv run python -m app.cli.download_models` — downloads embedding/tokenizer/Docling/picture/reranker models into `MODELS_DIR`; `--check`/`--force` flags; resumable (marker file only written on success) |
| Document upload/list API | ✅ | `POST /api/v1/documents` (needs `rag:ingest` scope, own rate limit `RATE_LIMIT_UPLOAD`, capped upload size `RAG_MAX_UPLOAD_MB`, streamed read), `GET /api/v1/documents` (needs `rag:query` scope) |
| RAG retrieval (dense/sparse/hybrid/reranked) | ✅ | `VectorRetriever`, `KeywordRetriever`, `HybridRetriever` (RRF), local `CrossEncoderReranker` / API reranker (`CohereReranker`, `VoyageReranker`), wired via `app/rag/retrieval/factory.py`. Exposed via `POST /api/v1/documents/search` (requires `rag:query` scope). |
| RAG generation + prompt templates | 📋 | Folder scaffolded (`app/rag/generation/`) |
| Document + Chunk data model (pgvector) | ✅ | `app/models/document.py`, `app/models/chunk.py` — 768-dim vectors (BAAI/bge-base), HNSW cosine index, verified against real Postgres |
| Multimodal ingestion (image/audio/video) | 📋 | Folders scaffolded (`app/multimodal/*`); `Document.source_type`/`Chunk.modality` already support non-text values |
| Retriever evaluation harness | 📋 | Folder scaffolded (`app/evaluation/retriever_eval/`) |
| Generation evaluation harness (faithfulness, relevance) | 📋 | Folder scaffolded (`app/evaluation/generation_eval/`) |

## Known limitations to resolve before production traffic

- Refresh-token lookup is a full active-token scan — needs a `token_id`
  prefix for O(1) lookup at scale.
- Rate limiter is in-memory (per-process) — needs a Redis-backed store
  before running more than one app replica.
- No secrets-manager integration — `.env`/mounted files only.
