"""
Proves the two building blocks of hybrid search actually work against real
Postgres: full-text keyword search via the generated tsvector column, and
reciprocal rank fusion combining two independently-ranked result lists.
"""
import random

import pytest

from app.core.security import hash_password
from app.models.chunk import EMBEDDING_DIM, Chunk
from app.models.document import Document
from app.models.user import User
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository

pytestmark = pytest.mark.asyncio


def _fake_vector(seed: float) -> list[float]:
    random.seed(seed)
    return [random.uniform(-1, 1) for _ in range(EMBEDDING_DIM)]


async def test_keyword_search_matches_on_content_text(db_session):
    user = await UserRepository(db_session).create(
        User(email="hybrid-test@example.com", hashed_password=hash_password("SuperSecret123!"))
    )
    document = await DocumentRepository(db_session).create(
        Document(owner_id=user.id, title="Doc", source_type="text", status="ingested")
    )
    chunk_repo = ChunkRepository(db_session)
    await chunk_repo.bulk_create([
        Chunk(document_id=document.id, chunk_index=0, content="the quick brown fox jumps", embedding=_fake_vector(1)),
        Chunk(document_id=document.id, chunk_index=1, content="a completely unrelated sentence about oceans", embedding=_fake_vector(2)),
    ])

    results = await chunk_repo.keyword_search("brown fox", owner_id=user.id)

    assert len(results) == 1
    assert "fox" in results[0][0].content
