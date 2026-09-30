from app.rag.retrieval.base import RetrievedChunk, reciprocal_rank_fusion


def test_reciprocal_rank_fusion_favors_items_ranked_highly_in_both_lists():
    a = RetrievedChunk(chunk_id="a", document_id="d", content="a", score=0)
    b = RetrievedChunk(chunk_id="b", document_id="d", content="b", score=0)
    c = RetrievedChunk(chunk_id="c", document_id="d", content="c", score=0)

    vector_ranked = [a, b, c]   # a is best by vector similarity
    keyword_ranked = [b, a, c]  # b is best by keyword match; a is still 2nd in both

    fused = reciprocal_rank_fusion([vector_ranked, keyword_ranked])

    # a and b both rank in the top 2 of both lists; c ranks last in both —
    # c must end up last in the fused result regardless of tie-break order.
    fused_ids = [chunk.chunk_id for chunk in fused]
    assert fused_ids[-1] == "c"
    assert set(fused_ids[:2]) == {"a", "b"}
