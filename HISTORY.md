# HISTORY.md

Append-only changelog. Every commit that changes behavior, structure, or
dependencies adds an entry here (see `AGENTS.md` Section 4). Newest entries
at the top. Do not rewrite or delete past entries — if something was
reverted, add a new entry saying so.

Format: `[MAJOR|MINOR] YYYY-MM-DD — summary`
- **MAJOR**: new capability, schema change, security-relevant change,
  breaking change to an existing contract.
- **MINOR**: refactor with no behavior change, doc update, dependency
  patch bump, test addition.

## 2026-09-30 (add document retrieval & reranking search endpoint)

- `[MAJOR]` Implemented concrete retrieval backends (`VectorRetriever`, `KeywordRetriever`, `HybridRetriever` using RRF) and rerankers (`CrossEncoderReranker`, `CohereReranker`, `VoyageReranker`) backed by `app/rag/retrieval/factory.py`. Added `POST /api/v1/documents/search` endpoint (`app/api/v1/endpoints/search.py`) gated with `rag:query` scope and rate-limited via `RATE_LIMIT_SEARCH`. Added reranker model download support in `app/cli/download_models.py`.

---

## 2026-09-29 (suppress Pydantic protected namespace warnings)

- `[MINOR]` Moved `warnings.filterwarnings` to line 1 of `app/main.py` before any application or third-party package imports, preventing pre-import Pydantic protected namespace `UserWarning`s from reaching stdout during server startup.

---

## 2026-09-27 (fix table/picture/heading loss; real embeddings; real HybridChunker; model downloader)

Follow-up to the ingestion pipeline built on 2026-09-26. Manual review of
that code (prompted by a user question about how tables/images/graphs were
handled) found the parser was silently dropping all of them. This entry
rebuilds parsing, chunking, and embedding properly.

- `[MAJOR]` **Fixed: tables and pictures were silently dropped.**
  `DoclingParser` only kept items with a `.text` attribute;
  `docling_core`'s `TableItem` and `PictureItem` have none, so both were
  skipped with no error — a table's numbers and a picture's caption never
  reached the database. Rewrote `flatten_docling_document()` to handle
  `TableItem` (exported to markdown via `export_to_markdown()`, caption
  prepended) and `PictureItem` (caption + optional VLM description)
  explicitly, and to track headings via `TitleItem`/`SectionHeaderItem`
  using a depth-keyed stack (this Docling version has no ancestor-lookup
  API). `ParsedDocument.metadata` now reports `pages`/`tables`/
  `pictures`/`pictures_described` and this is persisted onto
  `Document.doc_metadata` so it's visible per document — including when a
  picture's content did **not** make it into search.
- `[MAJOR]` **Fixed: `DoclingHybridChunker` never called Docling's
  `HybridChunker`.** It constructed one in `__init__` but the actual
  chunking logic was a hand-rolled loop that ignored it. Rewrote to call
  the real `HybridChunker.chunk()` and `.contextualize()`, so headings are
  part of the text that gets embedded and full-text indexed, oversized
  tables are split by row with the header repeated on each piece, and
  chunk `modality` reflects table/picture content correctly.
  `RAG_CHUNKER_TOKENIZER_MODEL` (previously dead config, read by nothing)
  now actually selects the tokenizer via `chunking/tokenizers.py`.
- `[MAJOR]` **Real embeddings are now the default**
  (`RAG_EMBEDDING_BACKEND=sentence_transformers`), loading BAAI/bge-base
  from a local `MODELS_DIR` folder rather than the HuggingFace cache —
  this also avoids the Windows symlink-permission error
  (`WinError 1314`) hit earlier, since `local_dir` downloads write real
  files, not symlinks. `SentenceTransformersEmbedder` checks the loaded
  model's actual output dimension against `EMBEDDING_DIMENSIONS` at load
  time and fails loudly on a mismatch, instead of pgvector rejecting
  inserts later with a confusing error.
- `[MAJOR]` Added `app/cli/download_models.py`
  (`uv run python -m app.cli.download_models`): downloads the embedding
  model, chunker tokenizer, Docling layout/table/OCR models, and (if
  enabled) the picture-description model into `MODELS_DIR`, based on
  what's actually configured in `.env`. `--check` reports what's missing
  without downloading; `--force` re-downloads. A per-model marker file is
  written only after a download succeeds, so an interrupted download is
  retried rather than mistaken for complete.
- `[MAJOR]` Added picture/chart description as a configurable, **off by
  default** enrichment step (`RAG_PICTURE_DESCRIPTION_ENABLED`): a
  vision-language model converts each picture to a text description,
  which becomes searchable chunk text. Two backends:
  `RAG_PICTURE_DESCRIPTION_BACKEND=local` (a local VLM, e.g.
  HuggingFaceTB/SmolVLM-256M-Instruct, downloaded like other models) or
  `=api` (an OpenAI-compatible endpoint — flagged as sending document
  images off-machine; `Settings` fails fast at startup if `api` is chosen
  without a URL/model configured). API keys use `SecretStr` so they never
  print in logs/reprs.
- `[MAJOR]` `IngestionService` now rejects unsupported file types before
  writing anything to disk or the database (previously it would create a
  `Document` row and a stored file, then fail during parsing). Uploads are
  read in capped 1&nbsp;MB pieces up to `RAG_MAX_UPLOAD_MB` instead of
  being pulled fully into memory first, and `/api/v1/documents` has its
  own `RATE_LIMIT_UPLOAD` limit (uploads run Docling + chunking +
  embedding — by far the most CPU-heavy endpoint in the API). Chunking
  (CPU-bound tokenization) now runs off the event loop via
  `asyncio.to_thread`, matching how parsing and embedding already did.
- `[MAJOR]` A missing model now fails with `ModelNotFoundError` (HTTP 503,
  message names the model and the exact fix command) instead of an
  unhandled exception deep in Docling/sentence-transformers' internals.
  Server filesystem paths are logged, never returned to a client.
- `[MINOR]` Moved the shared `slowapi` `Limiter` into
  `app/core/rate_limit.py` so `documents.py` can use the same instance
  `main.py` registers, instead of each router constructing its own.
- `[MINOR]` Added `app/tests/helpers/tiny_models.py`: builds a tiny,
  randomly-initialized tokenizer and sentence-transformers model with no
  network access, so unit tests exercise the real HuggingFace tokenizer
  and real `SentenceTransformer` loading code paths (not just interface
  mocks) in milliseconds. This says nothing about embedding *quality* —
  only the real BAAI/bge weights can confirm that.
- Added unit tests for the parser (table/picture/heading extraction,
  corrupt-file handling, missing-model errors), the chunker (headings and
  labelled table values in chunk text, table splitting, tokenizer
  selection), the embedder (real loading, normalization, dimension
  guard), pipeline options (picture-description config mapping,
  fail-fast validation, local-vs-remote-services), and the download
  command (skip-if-complete, resumability, missing-model reporting), plus
  integration tests for the full upload flow including the table/picture
  regression, unsupported-type rejection, oversized-upload rejection, and
  the missing-PDF-model 503 path.
- **Honesty note on verification**: per the instruction on this change,
  this rebuild was not run in the sandbox before packaging (only `ruff`
  and a syntax pass were done on the earlier, smaller edit in this same
  session — not on everything above). The code is believed correct based
  on the Docling/sentence-transformers/huggingface_hub APIs inspected
  directly from the installed packages during the *previous* session's
  investigation, but **run the test suite yourself** after unzipping
  before relying on this.

## 2026-09-26 (document ingestion pipeline: loading, parsing, chunking, embedding)

- `[MAJOR]` Built the full ingestion pipeline as four swappable stages
  behind interfaces in `app/rag/ingestion/base.py` (`FileStorage`,
  `DocumentParser`, `Chunker`, `EmbeddingGenerator`), matching the
  `Retriever`/`Reranker` pattern already used in `app/rag/retrieval/base.py`:
  - **Storage**: `LocalFileStorage` (`app/rag/ingestion/storage.py`) — raw
    uploaded files go on disk (or, later, S3/GCS behind the same
    interface), never as bytes in a Postgres row. Only the file URI is
    stored, in `Document.source_uri`.
  - **Parsing**: `DoclingParser` (`app/rag/ingestion/parsers/docling_parser.py`)
    using Docling's `DocumentConverter` for layout-aware parsing (headings,
    tables, paragraphs kept distinct, not flattened to one text blob).
    Heading context is tracked manually via a depth-keyed stack while
    iterating Docling's output, since this Docling version has no
    ancestor-lookup API.
  - **Chunking**: `DoclingHybridChunker`
    (`app/rag/ingestion/chunking/docling_chunker.py`) — merges chunks that
    share the same heading context up to a token budget, giving
    context-aware (not naive fixed-size) chunking. Added `SimpleChunker`
    (`chunking/simple_chunker.py`) as a network-independent fallback via
    `RAG_CHUNKER_BACKEND=simple`.
  - **Embedding**: `StubEmbeddingGenerator`
    (`embeddings/stub_embedder.py`, deterministic hash-seeded vectors, for
    pipeline testing only — never semantically meaningful) and
    `SentenceTransformersEmbedder` (`embeddings/sentence_transformers_embedder.py`,
    the real BAAI/bge-base implementation), selected via
    `RAG_EMBEDDING_BACKEND`.
  - `app/rag/ingestion/factory.py` builds all four from `Settings` — no
    hardcoded backend choice anywhere that uses them.
  - `IngestionService` (`app/rag/ingestion/pipeline.py`) orchestrates:
    save file -> create Document (`pending`) -> parse -> chunk -> embed ->
    bulk-save Chunks -> mark `ingested` (or `failed` on any exception).
  - New endpoints: `POST /api/v1/documents` (upload, requires `rag:ingest`
    scope) and `GET /api/v1/documents` (list own documents, requires
    `rag:query` scope) — `app/api/v1/endpoints/documents.py`.
- `[MAJOR]` Added `IngestionError` domain exception
  (`app/exceptions/base.py`), mapped to `422` in `handlers.py` — parsing/
  chunking failures are the uploaded file's fault, not a server error.
- `[MAJOR]` **Verified for real, not just written**: installed Docling
  2.87.0, confirmed `DocumentConverter` parses markdown/text fully offline
  (no model download needed), and got `HybridChunker` running fully
  offline too by supplying a custom `ApproxTokenizer` — Docling's default
  tokenizer needs a HuggingFace download this sandbox's network policy
  blocks. Ran a full HTTP upload through the real API
  (`test_document_ingestion.py`): register -> login -> upload a `.md` file
  -> confirmed `status="ingested"`, real chunks in Postgres, populated
  `content_tsv` (hybrid search) and 768-dim `embedding` columns. Passed.
  `SentenceTransformersEmbedder` (the real BAAI/bge path) is written
  correctly per the library's API and imports cleanly, but actual model
  download/inference is NOT exercised here — confirm in an environment
  with normal internet access.
- `[MAJOR]` **Schema management verified explicitly**: dropped the
  database entirely, replayed all 3 migrations from empty, then ran
  `alembic check` — confirmed **"No new upgrade operations detected"**,
  i.e. zero drift between the SQLAlchemy models and actual schema.
  - Fixed a real gap found in the process: the HNSW and GIN indexes
    (created via raw SQL in earlier migrations) weren't declared in
    `Chunk`'s SQLAlchemy metadata, so `alembic revision --autogenerate`
    incorrectly proposed dropping both of them on every single future
    migration. Fixed by declaring both via `Index(...)` in
    `Chunk.__table_args__`; confirmed the phantom drift is gone.
- `[MINOR]` Fixed two policy violations caught before packaging: `docling`
  had been added via `uv add docling` without an exact version (violates
  this project's own exact-pin rule — corrected to `docling==2.87.0` in
  `pyproject.toml`, re-locked). Also, `AuthService.register()`'s default
  scopes were `rag:query` only, missing `rag:ingest` — meaning a normally
  registered user could not use the new upload endpoint at all. Fixed to
  `rag:query,rag:ingest`.
- `[MINOR]` Added dependencies: `docling==2.87.0`, `pgvector==0.3.6` (added
  earlier), `sentence-transformers==3.3.1`, `aiofiles==24.1.0`.
- `[MINOR]` Added `data/uploads/` (via `LOCAL_STORAGE_DIR`) to `.gitignore`
  and as a named Docker volume in `docker-compose.yml`, so uploaded files
  survive container restarts in local dev.
- `[MINOR]` Added `app/tests/integration/test_document_ingestion.py`
  (full HTTP upload flow) — all 7 tests in the suite pass.

## Storage answer, for reference

Raw uploaded files: **local disk** (`LOCAL_STORAGE_DIR`, swappable for S3/
GCS later behind the same `FileStorage` interface) — never in Postgres.
Parsed/chunked text, embeddings, and metadata: **Postgres**, in the
`documents`/`chunks` tables, per the earlier pgvector decision.

## 2026-09-25 (retrieval layer: hybrid search + connection pooling + interfaces)

- `[MAJOR]` Added hybrid search support: `Chunk.content_tsv`, a Postgres
  GENERATED `tsvector` column (`to_tsvector('english', content)`), with a
  GIN index (`ix_chunks_content_tsv`). `ChunkRepository.keyword_search()`
  added alongside the existing `similarity_search()` — sparse (keyword)
  and dense (vector) retrieval now both exist as building blocks.
  - Migration gotcha found and fixed: autogenerate produced a **false
    positive** wanting to `DROP INDEX ix_chunks_embedding_cosine` (the
    HNSW index), because that index was created via raw `op.execute()` in
    the previous migration and SQLAlchemy's metadata has no record of it.
    Removed that incorrect drop by hand; verified both indexes survive a
    fresh `alembic upgrade head` from an empty DB.
- `[MAJOR]` Added `app/rag/retrieval/base.py`: `Retriever`/`Reranker`
  abstract interfaces, a backend-agnostic `RetrievedChunk` result type, and
  `reciprocal_rank_fusion()` — the standard way to merge two
  independently-ranked result lists (vector + keyword) whose raw scores
  aren't on comparable scales. No concrete `Retriever`/`Reranker`
  implementation yet (needs the embedding-generation step from ingestion,
  not built yet) — interfaces only, so ingestion/generation can be built
  against a stable contract.
- `[MAJOR]` Connection pooling made configurable: `DB_POOL_SIZE`,
  `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE` added to
  `app/core/config.py` and wired into `app/db/session.py` (previously
  hardcoded `pool_size=10, max_overflow=20`). Noted for later: if a
  connection pooler (PgBouncer) is placed in front of Postgres at the
  microservices stage and runs in transaction-pooling mode, asyncpg's
  prepared-statement cache must be disabled — not relevant yet (connecting
  directly to Postgres), documented for when it is.
- `[MINOR]` Added dynamic RAG settings (no more hardcoded literals in
  repository code): `RAG_DEFAULT_TOP_K`, `RAG_CHUNK_SIZE`,
  `RAG_CHUNK_OVERLAP`, `RAG_DISTANCE_METRIC`, `RAG_HYBRID_VECTOR_WEIGHT`.
- `[MINOR]` Considered LangGraph checkpointers/reducers per requirements
  discussion — deliberately **not implemented yet**: there's no
  graph/orchestration layer in `app/rag/generation/` for a checkpointer to
  checkpoint. Documented in `PRODUCTION_READINESS.md` for when that layer
  is built; it can reuse the same Postgres instance/pool via
  `langgraph-checkpoint-postgres`'s own `setup()`, no schema conflict with
  `documents`/`chunks`.
- `[MINOR]` Added `app/tests/integration/test_hybrid_search.py`
  (keyword search against real Postgres) and
  `app/tests/unit/test_retrieval.py` (reciprocal rank fusion, pure
  function). All 6 tests in the suite pass.
- Clarified (not a code change): current schema is multimodal-*ready*
  (`Document.source_type`/`Chunk.modality`) but not yet multimodal-
  *native* — all modalities are assumed to be converted to text (caption/
  OCR/transcript) before embedding with BAAI/bge-base. Native cross-modal
  embeddings (e.g. CLIP) would need a second vector column or table, since
  pgvector fixes dimension per column.

## 2026-09-25 (RAG data layer: documents + chunks + pgvector)

- `[MAJOR]` Added the first real RAG schema: `Document` (`app/models/document.py`)
  and `Chunk` (`app/models/chunk.py`) models, `DocumentRepository` and
  `ChunkRepository` (with `ChunkRepository.similarity_search()` using
  pgvector cosine distance). Vector storage decision: **pgvector on the
  existing Postgres instance** (not a separate vector DB), embedding
  dimension fixed at **768** to match the current embedding model
  (BAAI/bge-base via sentence-transformers, run locally). Added
  `EMBEDDING_DIMENSIONS` to `app/core/config.py` — documentation/runtime-
  assertion value only; the schema dimension is fixed by migration, not
  by this setting.
- `[MAJOR]` Installed and enabled the `pgvector` Postgres extension
  (`CREATE EXTENSION IF NOT EXISTS vector`, v0.6.0) and added the
  `pgvector==0.3.6` Python package. Generated migration
  `19196fe163e5_add_documents_and_chunks_tables.py` — **had to hand-patch
  the autogenerated file**: Alembic's autogenerate doesn't know how to
  emit `CREATE EXTENSION` (it only diffs tables/columns) and rendered the
  `Vector` column type without importing `pgvector.sqlalchemy`, which
  would have raised `NameError` at migration runtime. Also added an HNSW
  index (`ix_chunks_embedding_cosine`, `vector_cosine_ops`) by hand —
  index creation for pgvector isn't autogenerated either.
  - Verified for real: dropped and recreated the database from empty, ran
    `alembic upgrade head` end to end, confirmed the extension, both
    tables, and the HNSW index all exist via `psql`.
- `[MAJOR]` Added `app/tests/integration/test_rag_similarity_search.py` —
  inserts real 768-dim vectors, runs `ChunkRepository.similarity_search()`,
  asserts the near-identical vector ranks above the unrelated one. Passed.
- `[MINOR]` Added a `db_session` pytest fixture (`app/tests/integration/conftest.py`)
  for tests that exercise repositories directly rather than through the
  HTTP client; extended the `clean_db` autouse fixture to truncate
  `chunks`/`documents` alongside the existing auth tables.
- `[MINOR]` Switched the Postgres image in `docker-compose.yml` and the CI
  Postgres service (`.github/workflows/ci.yml`) from `postgres:16-alpine`
  to `pgvector/pgvector:pg16` — the extension has to be present in the
  image; installing it via apt (as done locally for testing) isn't an
  option in a container.

## 2026-09-24 (rate limiting hardened)

- `[MAJOR]` Extended rate limiting beyond `/auth/login` to close real DoS
  gaps found while reasoning through production readiness:
  - `/auth/register` — `RATE_LIMIT_REGISTER` (default `3/minute`). Every
    call runs a bcrypt hash; unlimited registration is a cheap
    CPU-exhaustion vector.
  - `/auth/refresh` — `RATE_LIMIT_REFRESH` (default `10/minute`). This is
    the most expensive endpoint to abuse today: it bcrypt-compares the
    presented token against every active refresh token in the DB
    (`AuthService._find_all_active_tokens`, a known O(n) scaling
    limitation — see `FEATURES.md`). Left unprotected, this was the
    cheapest CPU-exhaustion DoS vector in the whole API.
  - `/auth/logout` — `RATE_LIMIT_LOGOUT` (default `10/minute`).
  - Added `RATE_LIMIT_DEFAULT` (`60/minute`) applied to every route via
    `Limiter(default_limits=[...])` — defense in depth for any endpoint
    (including future RAG endpoints) that doesn't get an explicit limit.
  - Verified for real: hammered `/auth/register` with 4 rapid requests,
    confirmed `201, 201, 201, 429` — limit enforced correctly, not just
    configured.
- `[MINOR]` All limits are configurable via `.env`
  (`RATE_LIMIT_REGISTER`/`RATE_LIMIT_REFRESH`/`RATE_LIMIT_LOGOUT`/
  `RATE_LIMIT_DEFAULT`), consistent with the existing `RATE_LIMIT_LOGIN`
  pattern.
- Deferred to the production-readiness backlog (not done now, per current
  testing-phase scope): distributed rate-limit backend (Redis), so this
  still resets per-process if run across multiple replicas — acceptable
  for a single-instance testing setup, not for production.

## 2026-09-23 (scope split: RAG-only)

- `[MAJOR]` Scoped this project down to **RAG + auth only**, per decision
  to keep multimodal RAG and multi-agent as separate projects during
  early development, unified only at deployment time via shared JWT
  auth (see "Future: microservices split" in `README.md`).
  - Removed `app/agents/` (orchestrator, tools, memory) and
    `app/evaluation/agent_eval/` entirely.
  - Removed `AgentExecutionError` from `app/exceptions/base.py` and its
    mapping in `app/exceptions/handlers.py`.
  - Trimmed default/superuser scopes to `rag:query`, `rag:ingest` only —
    dropped `agent:execute`, `agent:tool:*` (`app/services/auth_service.py`).
  - Renamed project in `pyproject.toml`: `ai-platform` → `rag-platform`.
  - Updated `AGENTS.md`, `README.md`, `FEATURES.md` to describe RAG-only
    scope; kept `rag/`, `multimodal/`, `guardrails/`, and
    `evaluation/{retriever_eval,generation_eval}` as-is — these are all
    genuinely part of a multimodal RAG system regardless of agents.
  - Also fixed a stale doc reference: `AGENTS.md`/`auth_service.py`
    docstrings said `app.core.exceptions` (pre-refactor path); corrected
    to `app.exceptions`.

## 2026-09-23 (superuser CLI)

- `[MAJOR]` Added `app/cli/create_superuser.py` — a Django
  `createsuperuser`-equivalent. Goes through a new
  `AuthService.create_superuser()` method (bcrypt-hashed password, same
  path as normal registration), not a raw SQL insert. Grants `role="admin"`,
  a broad default scope set, and `is_verified=True`. Run via
  `uv run python -m app.cli.create_superuser`.
- `[MINOR]` Tried registering it as a `uv run createsuperuser` console
  script via `[project.scripts]` in `pyproject.toml` — reverted. Adding
  `[project.scripts]` makes uv treat the project as a buildable
  distribution, which requires a `[build-system]` table this project
  doesn't define; without it, dependency resolution silently dropped all
  of `[project.dependencies]` (found via `uv lock` resolving 18 packages
  instead of 58). Kept the simpler `uv run python -m app.cli.create_superuser`
  invocation instead, consistent with how Alembic/pytest are already run.
- `[MINOR]` Added `app/tests/integration/test_create_superuser.py` —
  verifies the created user has `role="admin"` and can successfully hit
  the `require_role("admin")`-gated route end to end.

## 2026-09-23 (later — restructure + verification)

- `[MAJOR]` Extracted `app/core/logging.py` and `app/core/exceptions.py` into
  their own top-level packages: `app/logging/` (config + request-ID
  middleware) and `app/exceptions/` (domain exceptions + centralized
  `register_exception_handlers`). `app/core/` now holds only bootstrap
  config and security. Auth endpoints no longer need per-route
  try/except — `AppError` subclasses are caught and mapped to HTTP status
  codes in one place (`app/exceptions/handlers.py`).
- `[MAJOR]` Added `app/utils/` (datetime, ID generation, pagination
  helpers) and removed duplicated `datetime.now(timezone.utc)`/
  `uuid.uuid4()` calls across models/security/services in favor of it.
- `[MAJOR]` **Bug found and fixed via manual end-to-end testing against
  real Postgres**: `create_access_token` could produce byte-identical
  JWTs when login and refresh happened within the same second, because
  RS256 signing is deterministic and the payload (`sub`, `role`, `scopes`,
  `exp`, `iat`) was identical at one-second timestamp granularity. Fixed
  by adding a unique `jti` claim to every issued access token. Confirmed
  via a 15x stress-run of the integration test (previously ~50% flaky)
  and a dedicated regression test (`app/tests/unit/test_security.py`).
- `[MINOR]` Fixed missing `email-validator` dependency (required by
  Pydantic's `EmailStr`, not previously pinned) via `uv add`.
- `[MINOR]` Pinned `bcrypt==4.0.1` — `passlib==1.7.4` is incompatible with
  `bcrypt>=4.1` (can't read its version metadata), which silently broke
  password hashing with a misleading "password too long" error. Found by
  actually running registration against a live DB, not just import-time
  checks.
- `[MINOR]` Fixed `alembic/env.py` to insert the project root onto
  `sys.path` so `alembic revision --autogenerate`/`upgrade` work regardless
  of invocation context.
- `[MINOR]` Added `app/tests/integration/conftest.py` — an autouse fixture
  that truncates `users`/`refresh_tokens` before each integration test.
  Without it, re-running the suite against the same DB failed
  intermittently on a `UNIQUE` constraint (leftover data from the previous
  run), which looked like a flaky test but was a real test-isolation gap.
- `[MINOR]` Generated and applied the first real Alembic migration
  (`create users and refresh_tokens`) against a locally running Postgres
  16 instance; verified tables exist via `psql`.
- `[MINOR]` Pinned `pytest-asyncio` fixture loop scope explicitly
  (`asyncio_default_fixture_loop_scope = "function"`) to remove a
  deprecation warning.

## 2026-09-23 (uv migration)

- `[MAJOR]` Migrated dependency management from `requirements.txt`/pip to
  **uv**. Added `pyproject.toml` with exact-pinned (`==`) runtime and dev
  dependencies, generated `uv.lock`.
  - Security-relevant: added `[tool.uv]` hardening —
    `prerelease = "disallow"` (never resolve alpha/beta/rc versions) and
    `exclude-newer = "7 days"` (rolling supply-chain cooldown; ignores any
    package version published in the last 7 days).
  - CI (`.github/workflows/ci.yml`) now runs `uv sync --locked` everywhere
    and has a dedicated `lockfile-check` job (`uv lock --check`) so
    `pyproject.toml`/`uv.lock` drift fails the build instead of silently
    re-resolving.
  - `Dockerfile` rewritten to install a pinned `uv` binary and run
    `uv sync --locked --no-dev` for reproducible image builds.
- `[MINOR]` Added `AGENTS.md` with setup, security, and workflow rules for
  AI coding agents (Antigravity IDE) working in this repo.
- `[MINOR]` Added `FEATURES.md` and this file (`HISTORY.md`) as living
  trackers, per new bookkeeping requirement in `AGENTS.md` Section 4.

## 2026-09-23 (earlier same day — initial scaffold)

- `[MAJOR]` Initial project scaffold: layered architecture
  (`api -> services -> repositories -> models`), async FastAPI + SQLAlchemy
  + Postgres, structured logging, centralized config.
- `[MAJOR]` Security-relevant: implemented JWT-based authentication —
  RS256 access tokens (15 min TTL, stateless) + opaque, rotating refresh
  tokens (hashed at rest, DB-revocable). Endpoints: register, login,
  refresh, logout.
- `[MAJOR]` Security-relevant: implemented RBAC via `role` (coarse) and
  `scopes` (fine-grained) fields on `User`, enforced via
  `require_role()`/`require_scopes()` FastAPI dependencies.
- `[MAJOR]` Security-relevant: added rate limiting (slowapi) on the login
  endpoint to mitigate brute-force attacks.
- `[MINOR]` Added Alembic (async engine) migration setup, wired to all
  ORM models via `alembic/env.py`.
- `[MINOR]` Scaffolded forward-looking module structure with roadmap
  READMEs for `rag/`, `agents/`, `multimodal/`, `guardrails/`,
  `evaluation/` — no implementation yet, interfaces/placeholders only.
- `[MINOR]` Added Docker Compose (app + Postgres + Redis) for local dev,
  and an integration test for the full auth flow
  (`app/tests/integration/test_auth_flow.py`).
