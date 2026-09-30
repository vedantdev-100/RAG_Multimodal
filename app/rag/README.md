# RAG module

## Ingestion — implemented

**One-time setup (needed before any real ingestion, not just PDFs):**
```
uv run python -m app.cli.download_models
```
Downloads whatever your `.env` is configured to use (embedding model,
chunker tokenizer, Docling layout/table/OCR models, and the
picture-description model if enabled) into `MODELS_DIR` (default:
`./models`). Everything after this runs with no internet access. Check
what's missing without downloading: `--check`. Re-download: `--force`.

- `ingestion/base.py` — interfaces: `FileStorage`, `DocumentParser`,
  `Chunker`, `EmbeddingGenerator`. `ParsedDocument` carries both a
  flattened `elements` list (for simple chunkers) and `native` — the
  parser's own rich document object, which a structure-aware chunker
  (Docling's `HybridChunker`) needs and a flattened view would lose.
- `ingestion/source_types.py` — maps an uploaded filename to a
  `source_type`; unsupported extensions are rejected before anything is
  written to disk or the database.
- `ingestion/model_paths.py` — resolves a HuggingFace repo id to its local
  folder under `MODELS_DIR`; raises `ModelNotFoundError` (HTTP 503, message
  names the missing model and the fix) if it isn't downloaded. No
  filesystem paths are ever returned to a client — only logged.
- `ingestion/storage.py` — `LocalFileStorage` (disk). Swap for S3/GCS later
  behind the same interface — see `PRODUCTION_READINESS.md`.
- `ingestion/parsers/docling_parser.py` — `DoclingParser`:
  - **Tables** are extracted as `modality="table"` elements: markdown with
    the caption prepended. Docling's `HybridChunker` re-serializes the same
    table with row/column labels ("Q2, Revenue = 120") so a value stays
    attached to its headers when embedded, and splits an oversized table by
    rows with the header repeated on each piece.
  - **Pictures/charts** are `modality="image"`. With
    `RAG_PICTURE_DESCRIPTION_ENABLED=true`, a vision-language model
    (local, via `RAG_PICTURE_DESCRIPTION_BACKEND=local`, or an
    OpenAI-compatible API via `=api`) generates a text description that
    becomes the searchable chunk text; a `Document.doc_metadata` field
    records `pictures` vs `pictures_described` so it's visible per document
    when a picture's content did **not** make it into search.
  - **Headings** are tracked as a depth-keyed stack while iterating
    Docling's output (this Docling version has no ancestor-lookup API) and
    travel with every element and every chunk.
  - Conversion runs in a worker thread (`asyncio.to_thread`), never on the
    event loop. A corrupt/unreadable file raises `IngestionError` with a
    message that never leaks a server filesystem path.
- `ingestion/chunking/tokenizers.py` — `build_tokenizer()` loads the REAL
  HuggingFace tokenizer of `RAG_CHUNKER_TOKENIZER_MODEL` from
  `MODELS_DIR` (`RAG_CHUNKER_TOKENIZER=huggingface`, the default), so chunk
  sizes match what the embedding model will actually see.
  `RAG_CHUNKER_TOKENIZER=approx` (word-count based, no model) remains for
  tests/offline use.
- `ingestion/chunking/docling_chunker.py` — `DoclingHybridChunker` now
  wraps Docling's **real** `HybridChunker` (it previously constructed one
  but never called it — a bug, now fixed) and uses `contextualize()`, so
  the heading path is part of the text that gets embedded *and* full-text
  indexed. `SimpleChunker` remains as an offline, non-context-aware
  fallback (`RAG_CHUNKER_BACKEND=simple`).
- `ingestion/embeddings/sentence_transformers_embedder.py` — the default
  backend now. Loads BAAI/bge-base from the local `MODELS_DIR` folder (not
  the HuggingFace cache — sidesteps the Windows symlink permission error),
  checks the model's real output dimension against `EMBEDDING_DIMENSIONS`
  at load time, and runs inference in a worker thread.
  `ingestion/embeddings/stub_embedder.py` (deterministic, not semantically
  meaningful) remains for tests via `RAG_EMBEDDING_BACKEND=stub`.
- `ingestion/factory.py` — builds all four backends from `Settings`; swap
  via `.env`, no code change. `ModelNotFoundError` from a factory function
  is never cached by `lru_cache`, so once `download_models` has run the
  very next request succeeds — no restart needed.
- `ingestion/pipeline.py` — `IngestionService`: rejects unsupported file
  types up front, saves the file, parses, chunks (off the event loop),
  embeds, persists chunks, and records parse statistics (page/table/picture
  counts) on `Document.doc_metadata`. Any failure marks the document
  `failed` rather than leaving it stuck at `processing`.
- API: `POST /api/v1/documents` (own `RATE_LIMIT_UPLOAD` limit and its own
  `RAG_MAX_UPLOAD_MB` size cap, enforced by streaming the body in capped
  chunks rather than reading it fully into memory first), `GET /api/v1/documents`.

**What's genuinely verified vs. not**, since the sandbox this was built in
has no internet access to HuggingFace: parsing/chunking of markdown, DOCX
(tables + pictures + headings), and plain text ran against real Docling and
real tokenizer code paths using a tiny locally-built tokenizer standing in
for BAAI/bge's tokenizer. The PDF path (needs the layout/table/OCR models)
and any real embedding/tokenizer output from the actual BAAI/bge weights
were **not** run end-to-end here — confirm both after running
`download_models` in an environment with normal internet access.

## Retrieval — interfaces done, no concrete Retriever yet

- `retrieval/base.py` — `Retriever`/`Reranker` interfaces,
  `RetrievedChunk`, `reciprocal_rank_fusion()`.
- `ChunkRepository.similarity_search()` (dense, pgvector cosine) and
  `.keyword_search()` (sparse, Postgres full-text) both exist and work,
  and now search real embedded/indexed text that includes table values and
  heading context.
- Not yet built: a concrete `HybridRetriever` combining both via RRF, and
  any `Reranker` implementation (e.g. a cross-encoder). See
  `PRODUCTION_READINESS.md`.

## Generation — not started

- `generation/` — empty. Prompt templates + LLM call wrapper, routed
  through `app/guardrails` both before and after the LLM call.
