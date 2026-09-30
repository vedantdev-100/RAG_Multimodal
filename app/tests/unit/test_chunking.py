"""
Docling's real HybridChunker, driven by the real HuggingFaceTokenizer code
path (loaded from a tiny local tokenizer — see app/tests/conftest.py).
What these pin down: headings travel with every chunk's text, tables keep
their values bound to column names, and modality reflects table content.
"""
import pytest
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

from app.core.config import Settings, get_settings
from app.exceptions import IngestionError, ModelNotFoundError
from app.rag.ingestion.base import ParsedDocument
from app.rag.ingestion.chunking.docling_chunker import DoclingHybridChunker
from app.rag.ingestion.chunking.tokenizers import ApproxTokenizer, build_tokenizer
from app.rag.ingestion.model_paths import local_model_path
from app.rag.ingestion.parsers.docling_parser import DoclingParser

pytestmark = pytest.mark.asyncio

MARKDOWN = b"""# Sales Report

Revenue grew in Q3.

## Results

| Quarter | Revenue | Growth |
|---------|---------|--------|
| Q1      | 100     | 5%     |
| Q2      | 120     | 20%    |

Closing paragraph after the table.
"""


async def parse(markdown: bytes = MARKDOWN) -> ParsedDocument:
    return await DoclingParser().parse(markdown, "report.md")


def test_default_tokenizer_is_the_real_huggingface_one_loaded_locally():
    assert isinstance(build_tokenizer(), HuggingFaceTokenizer)


async def test_chunks_carry_headings_and_labelled_table_values():
    chunker = DoclingHybridChunker(build_tokenizer())
    chunks = chunker.chunk(await parse())

    table_chunk = next(c for c in chunks if c.modality == "table")
    # Heading path is part of the text that gets embedded AND full-text indexed.
    assert "Sales Report" in table_chunk.content and "Results" in table_chunk.content
    # Each value stays attached to its row and column name.
    assert "Q2, Revenue = 120" in table_chunk.content
    assert table_chunk.metadata["headings"] == ["Sales Report", "Results"]
    assert "table" in table_chunk.metadata["labels"]


async def test_without_merging_a_table_is_its_own_chunk():
    chunker = DoclingHybridChunker(build_tokenizer(), merge_peers=False)
    chunks = chunker.chunk(await parse())

    table_chunks = [c for c in chunks if c.modality == "table"]
    assert len(table_chunks) == 1 and table_chunks[0].metadata["labels"] == ["table"]
    assert all(c.modality == "text" for c in chunks if c is not table_chunks[0])


async def test_oversized_table_splits_and_every_piece_still_names_its_columns():
    rows = "\n".join(f"| Q{i} | {100 + i} | {i}% |" for i in range(1, 60))
    big = f"# Big\n\n## Data\n\n| Quarter | Revenue | Growth |\n|---|---|---|\n{rows}\n".encode()
    tokenizer = HuggingFaceTokenizer.from_pretrained(
        model_name=str(local_model_path(get_settings().RAG_CHUNKER_TOKENIZER_MODEL)), max_tokens=60
    )
    chunks = DoclingHybridChunker(tokenizer, merge_peers=False).chunk(await parse(big))

    table_chunks = [c for c in chunks if c.modality == "table"]
    assert len(table_chunks) > 1
    assert all("Revenue" in c.content for c in table_chunks)


def test_approx_tokenizer_mode_needs_no_model():
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        JWT_PRIVATE_KEY_PATH="x",
        JWT_PUBLIC_KEY_PATH="x",
        RAG_CHUNKER_TOKENIZER="approx",
        RAG_CHUNKER_MAX_TOKENS=123,
    )
    tokenizer = build_tokenizer(settings)
    assert isinstance(tokenizer, ApproxTokenizer) and tokenizer.get_max_tokens() == 123


def test_missing_tokenizer_model_is_an_actionable_error_without_path_leak():
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        JWT_PRIVATE_KEY_PATH="x",
        JWT_PUBLIC_KEY_PATH="x",
        MODELS_DIR="/definitely/not/here",
        RAG_CHUNKER_TOKENIZER_MODEL="nope/missing",
    )
    with pytest.raises(ModelNotFoundError) as exc:
        build_tokenizer(settings)
    assert "app.cli.download_models" in str(exc.value)
    assert "/definitely/not/here" not in str(exc.value)


def test_hybrid_chunker_refuses_a_document_without_the_native_docling_object():
    with pytest.raises(IngestionError):
        DoclingHybridChunker(build_tokenizer()).chunk(ParsedDocument(elements=[]))
