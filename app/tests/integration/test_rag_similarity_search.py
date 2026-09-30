"""
Regression/smoke test for the RAG data layer: proves a Document + Chunks
can be created, embeddings stored, and cosine-distance similarity search
via ChunkRepository actually returns the nearest chunk first — through the
real repository code, not raw SQL.
"""
import random

import pytest

from app.models.document import Document
from app.models.chunk import Chunk, EMBEDDING_DIM
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.core.security import hash_password
from app.models.user import User

pytestmark = pytest.mark.asyncio


def _fake_vector(seed: float) -> list[float]:
    random.seed(seed)
    return [random.uniform(-1, 1) for _ in range(EMBEDDING_DIM)]


async def test_similarity_search_returns_nearest_chunk_first(db_session):
    user_repo = UserRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    chunk_repo = ChunkRepository(db_session)

    user = await user_repo.create(
        User(email="rag-smoke-test@example.com", hashed_password=hash_password("SuperSecret123!"))
    )
    document = await doc_repo.create(
        Document(owner_id=user.id, title="Test Doc", source_type="text", status="ingested")
    )

    query_vector = _fake_vector(seed=1.0)
    near_vector = [v + 0.001 for v in query_vector]  # nearly identical -> should rank first
    far_vector = _fake_vector(seed=999.0)  # unrelated -> should rank last

    await chunk_repo.bulk_create([
        Chunk(document_id=document.id, chunk_index=0, content="far chunk", embedding=far_vector),
        Chunk(document_id=document.id, chunk_index=1, content="near chunk", embedding=near_vector),
    ])

    results = await chunk_repo.similarity_search(query_vector, owner_id=user.id, top_k=2)

    assert len(results) == 2
    top_chunk, top_distance = results[0]
    assert top_chunk.content == "near chunk"
    assert top_distance < results[1][1]  # nearest is strictly closer than the second result
