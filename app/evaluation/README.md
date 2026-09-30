# Evaluation module (roadmap)

This project is RAG-only — no agent evaluation harness here (that lives in
the separate multi-agent project). Per-component eval harnesses, run in CI
on every PR touching the corresponding component:
- `retriever_eval/` — recall@k, MRR, context precision against a golden set.
- `generation_eval/` — faithfulness/groundedness, answer relevance
  (e.g. RAGAS-style metrics), toxicity/PII leakage checks.
