"""Picture description is configuration: these check it maps onto Docling's
options correctly, and that a bad combination fails at startup."""
import pytest
from docling.datamodel.pipeline_options import PictureDescriptionApiOptions, PictureDescriptionVlmOptions
from pydantic import ValidationError

from app.core.config import Settings
from app.rag.ingestion.model_paths import docling_models_dir
from app.rag.ingestion.parsers.docling_parser import build_pipeline_options


def make_settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        JWT_PRIVATE_KEY_PATH="x",
        JWT_PUBLIC_KEY_PATH="x",
        **overrides,
    )


def test_picture_description_is_off_by_default():
    settings = make_settings()
    pdf, convert = build_pipeline_options(settings)
    assert pdf.do_picture_description is False and convert.do_picture_description is False
    assert pdf.generate_picture_images is False
    assert pdf.artifacts_path == docling_models_dir(settings)  # local models, not the HF cache
    # DOCX/PPTX need no models here; a set artifacts_path would make Docling
    # reject every DOCX until models are downloaded (regression test).
    assert convert.artifacts_path is None


def test_local_picture_description_options():
    settings = make_settings(
        RAG_PICTURE_DESCRIPTION_ENABLED=True,
        RAG_PICTURE_DESCRIPTION_MODEL="HuggingFaceTB/SmolVLM-256M-Instruct",
        RAG_PICTURE_MIN_AREA=0.1,
    )
    pdf, convert = build_pipeline_options(settings)
    assert pdf.do_picture_description and convert.do_picture_description
    assert pdf.generate_picture_images is True  # the VLM needs the cropped images
    assert isinstance(pdf.picture_description_options, PictureDescriptionVlmOptions)
    assert pdf.picture_description_options.repo_id == "HuggingFaceTB/SmolVLM-256M-Instruct"
    assert pdf.picture_description_options.picture_area_threshold == 0.1
    assert pdf.enable_remote_services is False  # local backend never goes off-machine
    assert convert.artifacts_path == docling_models_dir(settings)  # the local VLM lives there


def test_api_picture_description_is_explicit_opt_in_and_keeps_key_secret():
    settings = make_settings(
        RAG_PICTURE_DESCRIPTION_ENABLED=True,
        RAG_PICTURE_DESCRIPTION_BACKEND="api",
        RAG_PICTURE_DESCRIPTION_API_URL="http://localhost:11434/v1/chat/completions",
        RAG_PICTURE_DESCRIPTION_API_MODEL="llava",
        RAG_PICTURE_DESCRIPTION_API_KEY="super-secret-key",
    )
    pdf, _ = build_pipeline_options(settings)
    assert isinstance(pdf.picture_description_options, PictureDescriptionApiOptions)
    assert pdf.picture_description_options.headers == {"Authorization": "Bearer super-secret-key"}
    assert pdf.enable_remote_services is True
    assert "super-secret-key" not in repr(settings)  # SecretStr: never logged by accident


def test_api_backend_without_url_fails_at_startup():
    with pytest.raises(ValidationError) as exc:
        make_settings(RAG_PICTURE_DESCRIPTION_ENABLED=True, RAG_PICTURE_DESCRIPTION_BACKEND="api")
    assert "RAG_PICTURE_DESCRIPTION_API_URL" in str(exc.value)


def test_ocr_and_table_structure_are_switchable():
    pdf, _ = build_pipeline_options(make_settings(RAG_OCR_ENABLED=False, RAG_TABLE_STRUCTURE_ENABLED=False))
    assert pdf.do_ocr is False and pdf.do_table_structure is False
