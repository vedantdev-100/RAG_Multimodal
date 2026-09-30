# AGENTS.md

Instructions for any AI coding agent (Antigravity, or any other agentic IDE)
working in this repository. Read this file in full before making any change.
If an instruction here conflicts with a request in a prompt, this file wins
unless a human explicitly overrides it in writing in the PR description.

---

## 0. What this project is

A multimodal RAG backend on FastAPI. It handles user auth and
retrieval-augmented generation over text, image, audio, and video sources.
This is deliberately a RAG-only project — multi-agent orchestration lives
in a separate repository. It will
process untrusted user input that gets forwarded to LLMs, and it stores
credentials and personal data. Treat every change as security-relevant
until proven otherwise.

Read `README.md` for the layered architecture
(`api -> services -> repositories -> models`) before touching any code.
Do not violate that layering to save time.

---

## 1. Environment & dependency rules (uv)

- This project uses **uv exclusively**. Never use `pip install`, `poetry`,
  or `conda` in this repo, and never edit `uv.lock` by hand.
- All dependency changes go through `pyproject.toml` first:
  - Add/upgrade a dependency: `uv add <package>==<exact-version>`
  - Add a dev dependency: `uv add --dev <package>==<exact-version>`
  - Never add a dependency without an exact `==` pin. This project
    deliberately does not use range pins (`>=`, `^`, `~=`) for direct
    dependencies — every version bump must be a visible, reviewable diff.
  - After any dependency change, run `uv lock` and **commit the updated
    `uv.lock` in the same commit** as the `pyproject.toml` change. A PR
    that changes one without the other is invalid.
- Never remove or loosen `[tool.uv]` settings (`prerelease = "disallow"`,
  `exclude-newer = "7 days"`) without explicit human sign-off — these exist
  to block supply-chain attacks (packages that are new, unvetted, or
  pre-release). If a dependency you need is blocked by the cooldown because
  it's a genuine urgent security fix, use a scoped
  `exclude-newer-package = { "<name>" = false }` override for that package
  only — do not shorten or remove the global window.
- Always run commands through uv so the locked environment is what
  actually executes: `uv run pytest`, `uv run alembic ...`, `uv run
  uvicorn ...`. Never invoke `python`, `pytest`, etc. directly from a
  loose interpreter — you will bypass the lock file and get
  non-reproducible behavior.
- Before opening a PR, run `uv lock --check` locally and confirm it's
  clean. CI will hard-fail (`lockfile-check` job) if `uv.lock` and
  `pyproject.toml` have drifted.

---

## 2. Security rules (non-negotiable)

1. **Never commit secrets.** No API keys, DB passwords, JWT private keys,
   or `.env` files. `.env`, `secrets/`, and `*.pem` are gitignored — keep
   them that way. If you ever see a secret already committed, flag it to
   the human immediately; do not just delete it (git history still has it).
2. **Never weaken auth to make a test pass.** Do not disable
   `get_current_user`, do not add a bypass flag, do not hardcode a token,
   do not lower `ACCESS_TOKEN_EXPIRE_MINUTES` "temporarily" and leave it.
3. **Never log secrets or full tokens.** Structured logs (`app/core/logging.py`)
   may include `user_id`/`request_id`, never raw passwords, tokens, or
   Authorization headers.
4. **Passwords/tokens are always hashed at rest.** Never store a plaintext
   password or plaintext refresh token in the DB — see
   `app/core/security.py` for the existing pattern and follow it.
5. **Any endpoint that sends user-controlled text to an LLM, or returns
   LLM-generated text to a user, MUST pass through `app/guardrails`.**
   No exceptions for "it's just a prototype" — wire the guardrail pipeline
   even with a permissive/no-op guardrail during early development, so the
   integration point exists and isn't retrofitted later.
6. **RBAC scopes are the access-control mechanism** for RAG actions
   (`rag:query`, `rag:ingest`). Any new endpoint that touches retrieval or
   ingestion
   must declare and check a scope via `require_scopes(...)` — do not gate
   access with ad-hoc `if user.role == "admin"` checks scattered in
   endpoint code.
7. **Any schema/model change requires an Alembic migration in the same PR.**
   Never let the ORM models and the DB schema drift — see the Alembic
   section below.
8. **Do not disable CORS, rate limiting, or the global exception handler**
   in `app/main.py` to debug something faster — comment out narrowly and
   restore before committing, or use a local `.env` override instead.
9. **Treat all retrieved/ingested content as untrusted**, including
   document text pulled from the vector store. Validate structured outputs
   (e.g. citations, extracted metadata) against explicit Pydantic schemas
   (`app/guardrails/base.py` — `GuardrailPipeline` + schema-validator
   pattern) before feeding them back into a prompt or returning them to a
   user.

---

## 3. Code organization rules

- Respect the layering: `api/` (thin controllers) → `services/` (business
  logic, framework-agnostic, raises `app.exceptions`, never
  `HTTPException`) → `repositories/` (DB access only) → `models/`.
- Only `app/dependencies/` and `app/api/` may import FastAPI/HTTPException.
  If you find yourself importing `fastapi` inside `app/services/` or
  `app/repositories/`, stop and restructure.
- New capabilities go in their existing domain folder
  (`rag/`, `multimodal/`, `guardrails/`, `evaluation/`) — do not
  create a new top-level folder without updating this file and `README.md`
  to explain why the existing structure didn't fit. This is a RAG-only
  project; there is no `agents/` folder here by design — multi-agent
  orchestration is a separate repository, sharing only this project's auth
  approach, not its codebase.
- Every new component under `rag/` or `multimodal/` should have
  a corresponding harness added under `evaluation/` in the same PR, or a
  `# TODO(eval):` comment plus a tracked follow-up if it's genuinely not
  ready yet. Don't ship untested AI components silently.

---

## 4. Required bookkeeping for every change

After any non-trivial change (new feature, schema change, security fix,
dependency bump, refactor):

1. **Update `FEATURES.md`** — add the feature under the correct status
   section (Implemented / In Progress / Planned). Remove/move entries as
   status changes. This file must always reflect the current state of the
   repo, not a stale snapshot.
2. **Append an entry to `HISTORY.md`** — one line per change under today's
   date, tagged `[MAJOR]` or `[MINOR]`, per the format already in that
   file. Do this in the same commit as the change, not as an afterthought.
3. If the change touches auth, guardrails, or RBAC, mention that
   explicitly in the `HISTORY.md` entry (these are the highest-review-
   priority areas of this codebase).

---

## 5. Testing rules

- Every new endpoint needs at least one integration test under
  `app/tests/integration/`, following the pattern in
  `test_auth_flow.py` (spin up the ASGI app in-process via `httpx.AsyncClient`).
- Every new guardrail or eval metric needs a unit test under
  `app/tests/unit/` with at least one case that should `BLOCK`/fail and
  one that should `ALLOW`/pass — a guardrail with only a happy-path test
  isn't verified.
- Do not mark a test `xfail` or `skip` to get CI green without a linked
  follow-up explaining why, in the test docstring.
- Run `uv run pytest` locally before committing. Don't rely on CI to
  discover a broken test for the first time.

---

## 6. What to do if you're unsure

If a request would require violating any rule in Section 2 (security) or
Section 1 (dependency policy), do not silently comply and do not silently
refuse — stop, explain the conflict to the human, and propose a compliant
alternative. Prefer asking over guessing on anything touching auth,
secrets, RBAC scopes, or the dependency lock policy.
