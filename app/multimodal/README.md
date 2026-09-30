# Multimodal module (roadmap)

- `image/`, `audio/`, `video/` — modality-specific preprocessing +
  embedding generation, each behind a common `MultimodalEncoder` interface
  so `rag/ingestion` can treat all modalities uniformly.
