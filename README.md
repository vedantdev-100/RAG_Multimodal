# RAG Platform — Multimodal RAG + Authentication

**Scope note:** this project is deliberately RAG-only. Multi-agent
orchestration lives in a separate repository. The two share the same auth
approach (RS256 JWT + RBAC scopes) so a token minted here can eventually be
verified by an agents service too, but they do not share a codebase — see
"Future: microservices split" below for how they're meant to come together
at deployment time.

## Why this structure

This repo is organized by **layer** (transport → business logic → data access) and by
**capability domain** (auth, rag, multimodal, guardrails, evaluation). This is
intentional so that:

- Adding a new RAG pipeline stage never touches auth/security code.
- Every AI-facing component (rag, multimodal) has a **matching evaluation module**
  from day one — evaluation is not bolted on after the fact.
- Guardrails (input validation, prompt-injection detection, output filtering, PII
  redaction) sit in their own layer and are invoked as middleware/dependencies, not
  scattered inline inside business logic.

```
ai-platform/
├── app/
│   ├── main.py                  # FastAPI app factory, middleware, startup/shutdown
│   ├── core/                    # bootstrap only: config (pydantic-settings), JWT/password security
│   ├── logging/                 # structlog config + request-ID correlation middleware
│   ├── exceptions/               # domain exception hierarchy + centralized HTTP-status mapping
│   ├── utils/                    # shared helpers: datetime, ID generation, pagination
│   ├── api/v1/                  # HTTP transport layer only — thin controllers
│   │   └── endpoints/
│   ├── dependencies/            # FastAPI Depends() — auth guards, DB sessions, rate limits
│   ├── schemas/                 # Pydantic request/response contracts (I/O validation)
│   ├── models/                  # SQLAlchemy ORM models (DB schema)
│   ├── repositories/            # DB access only, no business logic
│   ├── services/                # business logic — orchestrates repositories + rules
│   ├── cli/                     # operator commands (e.g. create_superuser)
│   ├── guardrails/              # input/output safety layer for all AI components
│   ├── rag/                     # ingestion / retrieval / generation pipelines
│   ├── multimodal/              # image / audio / video processing pipelines
│   ├── evaluation/              # per-component eval harnesses (retriever, generation)
│   └── tests/
│       ├── unit/
│       └── integration/
├── alembic/                     # DB migrations
├── AGENTS.md                    # rules for AI coding agents (Antigravity, etc.)
├── HISTORY.md                   # append-only changelog
├── FEATURES.md                  # living feature-status tracker
├── pyproject.toml / uv.lock      # dependency management (uv)
└── docker-compose.yml
```

Note: `AGENTS.md` is named for *AI coding agents* (Antigravity and similar
tools working on this codebase) — unrelated to multi-agent orchestration,
which this repo does not contain.

## Why `logging`, `exceptions`, and `utils` are separate top-level packages

They started as single files under `core/`. Split out once it became clear
each would keep growing independently of "bootstrap config" concerns:

- **`app/logging/`** — today: JSON log config + request-ID middleware.
  Will grow to hold per-component log adapters (retriever logs, eval-run
  logs) as those modules are built.
- **`app/exceptions/`** — `base.py` defines the `AppError` hierarchy;
  `handlers.py` maps every subtype to an HTTP status in ONE place via
  `register_exception_handlers(app)`. Endpoints raise domain exceptions
  and never need a try/except for them — see `app/api/v1/endpoints/auth.py`
  for the pattern.
- **`app/utils/`** — small, dependency-free helpers (`utcnow()`,
  `generate_uuid()`, pagination) used across models/services so timestamp
  and ID generation logic lives in exactly one place.

`app/core/` now holds only two things: `config.py` (centralized,
fail-fast settings) and `security.py` (password hashing, JWT
issuance/verification) — the two things every other module bootstraps
from.

## Layering rule (enforced by convention + code review)

`api` → `services` → `repositories` → `models`
`api` may depend on `schemas`, `dependencies`, `services`.
`services` may depend on `repositories`, `schemas`, `guardrails`, `core`.
`repositories` may depend on `models`, `db` only.
**Never** import a repository directly inside an endpoint. **Never** put SQL/ORM
logic inside a service.

## Auth flow implemented in this scaffold

1. `POST /api/v1/auth/register` — creates user, hashes password (bcrypt), assigns
   default role `user` and scopes `rag:query,rag:ingest`.
2. `POST /api/v1/auth/login` — verifies credentials, issues a short-lived **access
   token** (RS256, 15 min) + a **refresh token** (rotated, stored hashed in DB, 7 days).
3. `POST /api/v1/auth/refresh` — validates refresh token against DB hash, rotates it
   (old one is revoked), issues a new access token.
4. `POST /api/v1/auth/logout` — revokes the refresh token.
5. `GET /api/v1/users/me` — protected route, demonstrates `get_current_user` +
   role/scope-based authorization dependency.
6. `uv run python -m app.cli.create_superuser` — operator CLI to create an
   `admin` account directly, no HTTP endpoint exposed for it.

## Why RS256 instead of HS256

HS256 uses one shared secret for signing and verification — fine for a monolith, but
this project is designed to eventually run as one of several services (see below)
that all need to **verify** tokens without needing the ability to
**mint** them. RS256 gives you that asymmetry: only the auth issuer holds the
private key; every other service ships with just the public key.

## Dependency management (uv)

This project uses [uv](https://docs.astral.sh/uv/) exclusively — no pip,
poetry, or conda. See `AGENTS.md` for the full rules if you're an AI agent
working in this repo; the short version for humans:

```bash
uv sync --locked        # install exact locked dependencies (use this, not `uv sync`)
uv run uvicorn app.main:app --reload
uv run pytest
uv run alembic upgrade head
```

All dependencies in `pyproject.toml` are exact-pinned (`==`), and
`[tool.uv]` enforces `prerelease = "disallow"` plus a 7-day
`exclude-newer` supply-chain cooldown. `uv.lock` is committed and CI runs
`uv sync --locked` + `uv lock --check`, so a lock/pyproject mismatch fails
the build instead of silently re-resolving. See `HISTORY.md` for when/why
this was set up and `FEATURES.md` for current status.

## Other project docs

- `AGENTS.md` — rules for AI coding agents working in this repo (security,
  dependency policy, layering, required bookkeeping).
- `HISTORY.md` — append-only changelog of major/minor changes.
- `FEATURES.md` — living status table of implemented/in-progress/planned
  features.
- `PRODUCTION_READINESS.md` — deferred checklist for the microservices/
  production phase (rate limiting is done now; everything else there is
  intentionally not implemented yet).

## Next steps (in order)

1. Wire up `guardrails/` middleware (prompt-injection + PII filters) on any endpoint
   that accepts free text destined for an LLM.
2. Implement `rag/ingestion` and `rag/retrieval` behind a vector-store-agnostic
   interface (repository pattern applies here too).
3. Implement `rag/generation` with prompt templates, routed through
   `guardrails` both before the LLM call (input) and after (output).
4. Add `evaluation/*` harnesses wired into CI so regressions in retrieval or
   generation quality are caught pre-merge.

## Future: microservices split

This is early-stage/dev — everything runs as one FastAPI app against one
Postgres instance. The RS256 keypair choice and the RBAC scope design
(`rag:*` namespaced scopes) exist specifically so this can later split into
independently deployable services without a token-format rewrite. See the
separate microservices plan discussed for the deployment-time architecture
(auth, RAG, and agents as separate services under Kubernetes) — no code
changes for that are made in this repo yet.
