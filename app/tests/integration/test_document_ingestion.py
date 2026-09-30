"""
End-to-end ingestion through the real HTTP API and real Postgres.

Pipeline under test: real Docling parsing -> Docling HybridChunker (real
HuggingFaceTokenizer code path, tiny local tokenizer) -> stub embeddings ->
pgvector + tsvector storage. Embedding QUALITY (real BAAI/bge) and the PDF
model path can't be exercised without downloaded models; everything
else here is the production code path.
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.chunk import Chunk
from app.repositories.chunk_repository import ChunkRepository

pytestmark = pytest.mark.asyncio

MARKDOWN_WITH_TABLE = b"""# Sales Report

Revenue grew in Q3.

## Results

| Quarter | Revenue | Growth |
|---------|---------|--------|
| Q1      | 100     | 5%     |
| Q2      | 120     | 20%    |

![Revenue chart](chart.png)

Closing paragraph after the figure.
"""


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def sign_in(client, email="ingest-test@example.com") -> dict:
    credentials = {"email": email, "password": "SuperSecret123!"}
    assert (await client.post("/api/v1/auth/register", json=credentials)).status_code == 201
    response = await client.post("/api/v1/auth/login", json=credentials)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def upload(client, headers, name, content, mime="text/markdown"):
    return await client.post("/api/v1/documents", headers=headers, files={"file": (name, content, mime)})


async def test_table_values_headings_and_picture_stats_survive_ingestion(client, db_session):
    headers = await sign_in(client)
    owner_id = (await client.get("/api/v1/users/me", headers=headers)).json()["id"]

    response = await upload(client, headers, "report.md", MARKDOWN_WITH_TABLE)
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["status"] == "ingested" and document["source_type"] == "md"
    # Visible per-document record of what the parser found. One picture was
    # present but (description off) is NOT searchable — the numbers say so.
    assert document["doc_metadata"]["tables"] == 1
    assert document["doc_metadata"]["pictures"] == 1
    assert document["doc_metadata"]["pictures_described"] == 0
    assert document["doc_metadata"]["chunks"] >= 1

    chunks = list((await db_session.execute(select(Chunk).where(Chunk.document_id == document["id"]))).scalars())
    table_chunk = next(c for c in chunks if c.modality == "table")
    assert "Q2, Revenue = 120" in table_chunk.content  # value still bound to its row/column
    assert "Results" in table_chunk.content  # heading path is part of the stored/embedded text
    assert all(len(c.embedding) == 768 for c in chunks)
    assert all(c.content_tsv is not None for c in chunks)

    # Hybrid-search payoff: because headings and table cells are in the
    # indexed text, keyword search finds the table by a heading word and by
    # a cell value. (Before the fix both were dropped and this found nothing.)
    repo = ChunkRepository(db_session)
    assert await repo.keyword_search("Results", owner_id=owner_id)
    hits = await repo.keyword_search("Growth", owner_id=owner_id)
    assert any(c.modality == "table" for c, _rank in hits)


async def test_plain_text_upload_works(client):
    headers = await sign_in(client)
    response = await upload(client, headers, "notes.txt", b"Plain text notes.\n\nSecond paragraph.", "text/plain")
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "ingested"


async def test_unsupported_type_is_rejected_before_anything_is_stored(client):
    headers = await sign_in(client)
    response = await upload(client, headers, "malware.exe", b"MZ...", "application/octet-stream")
    assert response.status_code == 422
    assert "Supported types" in response.json()["detail"]
    listing = (await client.get("/api/v1/documents", headers=headers)).json()
    assert listing["total"] == 0  # no Document row, no orphan file


async def test_oversized_upload_is_rejected(client):
    headers = await sign_in(client)
    response = await upload(client, headers, "huge.md", b"x" * (2 * 1024 * 1024))  # cap is 1 MB in tests
    assert response.status_code == 413


async def test_pdf_without_models_is_a_503_with_the_fix_and_the_document_is_marked_failed(client):
    headers = await sign_in(client)
    response = await upload(client, headers, "scan.pdf", b"%PDF-1.4 fake", "application/pdf")
    assert response.status_code == 503
    assert "app.cli.download_models" in response.json()["detail"]
    documents = (await client.get("/api/v1/documents", headers=headers)).json()["documents"]
    assert [d["status"] for d in documents] == ["failed"]


async def test_upload_requires_authentication(client):
    response = await upload(client, {}, "a.md", b"# hi")
    assert response.status_code == 401
