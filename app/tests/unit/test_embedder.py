"""
SentenceTransformersEmbedder loading a REAL sentence-transformers model
from a local folder (a tiny random one built by the fixture). Verifies the
loading path, batching, normalisation, and the dimension guard. Says
nothing about embedding quality — only the real bge model can.
"""
import math

import pytest

from app.rag.ingestion.embeddings.sentence_transformers_embedder import SentenceTransformersEmbedder

pytestmark = pytest.mark.asyncio


async def test_embeds_to_normalised_vectors_of_the_configured_size(tiny_st_dir):
    embedder = SentenceTransformersEmbedder(tiny_st_dir, dimensions=32, batch_size=2)
    vectors = await embedder.embed(["revenue growth q1", "sales chart data", "summary of results"])

    assert len(vectors) == 3 and all(len(v) == 32 for v in vectors)
    for vector in vectors:
        assert math.isclose(sum(x * x for x in vector), 1.0, abs_tol=1e-4)  # cosine-ready


async def test_same_text_gives_same_vector_and_different_text_differs(tiny_st_dir):
    embedder = SentenceTransformersEmbedder(tiny_st_dir, dimensions=32)
    a, b, a_again = await embedder.embed(["revenue growth", "chart data table", "revenue growth"])
    assert a == a_again
    assert a != b


async def test_empty_input_returns_empty_list(tiny_st_dir):
    assert await SentenceTransformersEmbedder(tiny_st_dir, dimensions=32).embed([]) == []


def test_dimension_mismatch_with_the_database_column_fails_at_load_time(tiny_st_dir):
    with pytest.raises(ValueError) as exc:
        SentenceTransformersEmbedder(tiny_st_dir, dimensions=768)
    assert "EMBEDDING_DIMENSIONS=768" in str(exc.value) and "32-dim" in str(exc.value)
