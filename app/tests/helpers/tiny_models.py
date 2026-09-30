"""
Tiny, randomly-initialised stand-ins for real models, built on the fly
with no network access. They let tests exercise the REAL code paths —
HuggingFaceTokenizer, SentenceTransformer loading, dimension checks —
in milliseconds. They say nothing about embedding QUALITY; that can only
be judged with the real BAAI/bge model.
"""
from pathlib import Path

TINY_WORDS = (
    "revenue growth quarter sales report results table chart data the a of in and "
    "q1 q2 q3 q4 rose from to increase decrease total summary section details value "
    "paragraph text first second closing figure heading item row column"
).split()
SPECIALS = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"]


def _vocab() -> dict[str, int]:
    return {token: i for i, token in enumerate(SPECIALS + TINY_WORDS)}


def write_tiny_tokenizer(path: Path) -> Path:
    from tokenizers import Tokenizer, models, normalizers, pre_tokenizers
    from transformers import PreTrainedTokenizerFast

    path.mkdir(parents=True, exist_ok=True)
    tokenizer = Tokenizer(models.WordLevel(_vocab(), unk_token="[UNK]"))
    tokenizer.normalizer = normalizers.Lowercase()
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    PreTrainedTokenizerFast(
        tokenizer_object=tokenizer,
        unk_token="[UNK]",
        pad_token="[PAD]",
        cls_token="[CLS]",
        sep_token="[SEP]",
        mask_token="[MASK]",
    ).save_pretrained(str(path))
    return path


def write_tiny_sentence_transformer(path: Path, dimensions: int = 32) -> Path:
    import torch
    from sentence_transformers import SentenceTransformer, models
    from transformers import BertConfig, BertModel

    write_tiny_tokenizer(path)
    torch.manual_seed(0)
    config = BertConfig(
        vocab_size=len(_vocab()),
        hidden_size=dimensions,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=64,
        max_position_embeddings=64,
    )
    BertModel(config).save_pretrained(str(path))
    transformer = models.Transformer(str(path), max_seq_length=32)
    pooling = models.Pooling(transformer.get_word_embedding_dimension(), pooling_mode="cls")
    SentenceTransformer(modules=[transformer, pooling, models.Normalize()]).save(str(path))
    return path
