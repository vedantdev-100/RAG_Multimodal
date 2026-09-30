# PRODUCTION_READINESS.md

Deferred work list — **nothing here is implemented yet**. This is a
checklist to work through when moving from single-instance testing to the
microservices deployment (auth-service / rag-service / agents-service on
Kubernetes). Rate limiting/DoS hardening was pulled out of this list and
implemented now (see `HISTORY.md`, 2026-09-24 entry) since it was cheap
and useful even in testing.

Grouped by what triggers the need for it — do the group when that trigger
happens, not necessarily all at once.

## Trigger: building the RAG orchestration/generation layer

- [ ] **LangGraph checkpointers/reducers**, if the RAG pipeline becomes a
  multi-step graph (retrieve → rerank → generate → self-critique, etc.)
  rather than a single linear call. Deliberately not added now — there's
  no graph in `app/rag/generation/` yet for a checkpointer to checkpoint.
  When it's built: add `langgraph-checkpoint-postgres`, point it at the
  same `settings.DATABASE_URL`/pool already in use, call its own
  `setup()` once at startup. It manages its own tables independently of
  the Alembic-managed `documents`/`chunks` schema — no conflict expected,
  but confirm no table-name collision before wiring it in.
- [ ] **Concrete `Retriever`/`Reranker` implementations.**
  `app/rag/retrieval/base.py` defines the interfaces and
  `reciprocal_rank_fusion()`; nothing implements `Retriever` yet. Now that
  the ingestion pipeline populates real embeddings, a `HybridRetriever`
  combining `ChunkRepository.similarity_search()` + `.keyword_search()`
  via RRF is the natural first implementation.
- [ ] **Confirm the real model paths end to end in an environment with
  internet access.** `download_models`, `SentenceTransformersEmbedder`,
  the real HuggingFace tokenizer path, Docling's PDF pipeline (layout,
  table structure, OCR), and picture description (local VLM and/or the
  API backend) were all built and unit-tested against tiny local
  stand-ins, but never run against the real BAAI/bge weights or a real
  PDF — this sandbox has no HuggingFace network access. Run
  `uv run python -m app.cli.download_models` there, then re-run the
  ingestion tests, then manually upload a real PDF with a table and a
  chart before trusting this in anything beyond local testing.
- [ ] **Native multimodal embeddings** (e.g. CLIP for images) if
  captioning/description-then-text-embedding turns out to be
  insufficient. Needs a second `vector(N)` column or a separate table —
  pgvector fixes dimension per column, so this isn't a settings change.
- [ ] **Picture description cost/latency at scale.** It's off by default
  because it adds real per-picture time (and, on the `api` backend,
  external network calls) to every ingestion. Before enabling it broadly:
  decide whether it runs synchronously in the upload request (current
  behavior) or is moved to a background job so a document with many
  pictures doesn't hold the upload request open for a long time.

## Trigger: running more than one replica of any service

- [ ] **Object storage for uploaded files** (S3/GCS via a new `FileStorage`
  implementation). `LocalFileStorage` writes to a local disk path — fine
  for one instance/pod, but not shared across replicas. The interface
  (`app/rag/ingestion/base.py`) already supports swapping this in without
  touching `IngestionService` or the API layer.
- [ ] **Shared model storage across replicas.** `MODELS_DIR` is a local
  folder; each pod needs its own copy (baked into the image, or a shared
  read-only volume/PVC) rather than each one re-running
  `download_models` independently.
- [ ] **Move rate limiting to a shared backend (Redis).** Current setup
  (`slowapi`, in-memory) resets per-process — correct on 1 instance, silently
  weaker (`limit × replica count`) on N instances. Config already exists
  (`RATE_LIMIT_*` in `.env`); only the storage backend needs to change
  (`Limiter(storage_uri="redis://...")`).
- [ ] **Access-token revocation via Redis blacklist.** Today, logout/refresh
  revokes the *refresh* token but the old *access* token stays valid until
  its own 15-min expiry (confirmed behavior, not a bug — but not
  production-acceptable for "kill this session now" requirements). Add:
  on logout/refresh, write the old token's `jti` to a Redis set with TTL =
  remaining token lifetime; check that set in `get_current_user`.
- [ ] **Distributed session/idempotency handling** if any endpoint becomes
  non-idempotent under retries (matters more once RAG ingestion jobs exist).

## Trigger: splitting into separate services (auth / rag / agents)

- [ ] **JWKS endpoint on the auth service** (`/.well-known/jwks.json`)
  instead of distributing the raw public key file — lets rag-service and
  agents-service fetch/rotate the verification key without a redeploy.
- [ ] **Add `kid` (key ID) header to issued JWTs** and support multiple
  active public keys — required for zero-downtime key rotation.
- [ ] **Add `aud` (audience) and `iss` (issuer) claims**, and verify them on
  decode. Without this, a token minted for one service is technically
  valid against any other verifier — fine with one service, a real gap
  with three.
- [ ] **Service-to-service auth** for internal calls (e.g. agents-service
  calling rag-service as a tool): either forward the user's JWT, or mint a
  short-lived `role="service"` token, or use mTLS at the mesh level —
  decide before writing that integration, not after.
- [ ] **Per-service database ownership.** Each service should own its own
  tables (`auth-service` → `users`/`refresh_tokens`; `rag-service` →
  documents/chunks/embeddings) rather than reaching across.
- [ ] **Extract `app/core/security.py` + auth endpoints** into the
  standalone auth-service — this is the first concrete extraction step
  when the split actually happens.

## Trigger: real user traffic / going to production

- [ ] **Refresh-token theft detection.** If a revoked/expired refresh token
  is presented, treat it as a signal of possible theft — revoke the entire
  token family for that user and force re-login, not just reject the one
  request.
- [ ] **Account lockout / distributed brute-force detection.** Per-IP rate
  limiting doesn't stop a distributed attacker using many IPs against one
  account. Add a per-account failed-login counter with backoff.
- [ ] **Password policy beyond length.** Check against common/breached
  password lists (e.g. HaveIBeenPwned's k-anonymity API) at minimum.
- [ ] **Fix the refresh-token O(n) lookup.** `AuthService._find_all_active_tokens`
  scans every active token and bcrypt-compares each — fine at low volume,
  a real bottleneck (and rate-limiting is only a mitigation, not a fix) at
  scale. Switch to a `token_id.secret` composite so lookup is indexed.
- [ ] **Audit logging for security-relevant events** — logins, logouts,
  role changes, failed auth — with enough context (who, when, source IP)
  to support an incident review. Current structured logs cover some of
  this but weren't designed as an audit trail specifically.
- [ ] **Secrets management** — move JWT keys and DB credentials from
  `.env`/mounted files to a proper secrets manager (Vault, AWS Secrets
  Manager, or Kubernetes Secrets + external-secrets-operator) with
  rotation support.
- [ ] **Observability** — metrics (auth failure rate, token issuance rate,
  429 rate) and tracing (OpenTelemetry), not just structured logs. Needed
  to *detect* an attack in progress, not just log it after the fact.
- [ ] **Email verification and password reset flows** — `is_verified`
  field already exists on `User`; no email-sending integration yet.
- [ ] **MFA** — not started, lower priority than the above for an
  auth-under-attack scenario specifically.
- [ ] **Adversarial test coverage** — forged tokens (`alg: none`,
  algorithm confusion), concurrent refresh races, clock-skew edge cases,
  malformed/oversized payloads. Current test suite (3 tests) covers the
  happy path and one regression; a production auth system needs explicit
  negative-path tests for each of these.

## Explicitly not on this list (already handled)

RS256 signing, bcrypt password hashing, refresh-token hashing/rotation,
RBAC via role+scopes, unique `jti` per access token, centralized exception
handling, exact-pinned dependencies with supply-chain cooldown, and now
per-route rate limiting with a global default — all already implemented
and verified against real Postgres.
