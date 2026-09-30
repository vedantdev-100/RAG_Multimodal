import pytest

from app.tests.helpers.tiny_models import write_tiny_sentence_transformer


@pytest.fixture(scope="session")
def tiny_st_dir(tmp_path_factory):
    """A real (randomly initialised) sentence-transformers model, 32-dim."""
    return write_tiny_sentence_transformer(tmp_path_factory.mktemp("models") / "tiny-st", dimensions=32)
