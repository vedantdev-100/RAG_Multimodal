"""
The download command's logic, with the network call replaced by a fake that
just writes a file (real downloads need HuggingFace access).
"""
from app.cli import download_models as cli
from app.core.config import Settings


def make_settings(models_dir, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        JWT_PRIVATE_KEY_PATH="x",
        JWT_PUBLIC_KEY_PATH="x",
        MODELS_DIR=str(models_dir),
        **overrides,
    )


def test_download_is_skipped_when_complete_and_resumable_when_not(tmp_path, monkeypatch):
    calls = []

    def fake_snapshot_download(*, repo_id, local_dir, allow_patterns, force_download):
        calls.append(repo_id)
        (tmp_path / "org--name" / "config.json").write_text("{}")

    monkeypatch.setattr(cli, "snapshot_download", fake_snapshot_download)
    target = tmp_path / "org--name"

    assert cli.download_hf_repo("org/name", target) is True
    assert cli.download_hf_repo("org/name", target) is False  # marker present -> skipped
    assert cli.download_hf_repo("org/name", target, force=True) is True
    assert cli.download_hf_repo("org/name", target, allow_patterns=["tokenizer*"]) is True  # different request
    assert calls == ["org/name"] * 3


def test_interrupted_download_is_not_mistaken_for_complete(tmp_path, monkeypatch):
    def failing_download(**kwargs):
        (tmp_path / "org--name").mkdir(exist_ok=True)
        (tmp_path / "org--name" / "half.bin").write_text("partial")
        raise ConnectionError("network dropped")

    monkeypatch.setattr(cli, "snapshot_download", failing_download)
    try:
        cli.download_hf_repo("org/name", tmp_path / "org--name")
    except ConnectionError:
        pass
    assert not (tmp_path / "org--name" / cli.MARKER_NAME).exists()  # so the next run retries


def test_missing_models_reports_exactly_what_the_config_needs(tmp_path):
    settings = make_settings(tmp_path, RAG_EMBEDDING_BACKEND="sentence_transformers")
    missing = cli.missing_models(settings)
    assert any("embedding model" in m for m in missing)
    assert any("chunker tokenizer" in m for m in missing)
    assert any("docling" in m for m in missing)

    # Stub embeddings + approx tokenizer + non-local Docling need nothing on disk.
    lean = make_settings(
        tmp_path,
        RAG_EMBEDDING_BACKEND="stub",
        RAG_CHUNKER_TOKENIZER="approx",
        RAG_DOCLING_LOCAL_MODELS_ONLY=False,
    )
    assert cli.missing_models(lean) == []


def test_picture_model_is_only_required_when_the_feature_is_on(tmp_path):
    base = dict(RAG_EMBEDDING_BACKEND="stub", RAG_CHUNKER_TOKENIZER="approx")
    (tmp_path / "docling").mkdir()
    (tmp_path / "docling" / "layout.bin").write_text("x")

    assert cli.missing_models(make_settings(tmp_path, **base)) == []
    enabled = make_settings(tmp_path, RAG_PICTURE_DESCRIPTION_ENABLED=True, **base)
    assert any("picture-description" in m for m in cli.missing_models(enabled))


def test_a_failing_step_reports_failure_and_does_not_crash(capsys):
    def boom():
        raise ConnectionError("offline")

    assert cli._run_step("some model", boom) is False
    assert "[FAIL] some model" in capsys.readouterr().err
