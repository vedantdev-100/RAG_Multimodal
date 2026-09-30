"""
Shared test fixtures.

`clean_db` truncates all app tables before every test so tests are
independent of execution order and don't fail on a re-run due to leftover
data from a previous run (e.g. a UNIQUE constraint on email).

It also disposes the SQLAlchemy engine's connection pool after each test.
Why this matters: pytest-asyncio gives each test function its own event
loop by default, but asyncpg connections are bound to the loop that
created them. Without disposing the pool, a connection opened during test
A's loop gets reused (or pre-pinged) during test B's *different* loop and
raises "Future attached to a different loop" / "Event loop is closed" —
this is not flakiness, it's a structural mismatch between a
function-scoped event loop and a session-lived connection pool. Disposing
after every test forces fresh connections on the next test's loop.

`db_session` gives tests that talk to repositories directly (not through
the HTTP client) a session bound to the current test's event loop.
"""
import pytest_asyncio
from sqlalchemy import text

from app.db.session import AsyncSessionLocal, engine


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    async with engine.begin() as conn:
        await conn.execute(text(
            'TRUNCATE TABLE chunks, documents, refresh_tokens, users RESTART IDENTITY CASCADE'
        ))
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session
        await session.close()
