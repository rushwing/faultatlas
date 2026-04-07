from app.retrieval.context_builder import build_context


def test_build_context_respects_budget() -> None:
    results = [
        {"chunk_id": str(i), "document_id": "d1", "content": "x" * 1000, "score": 1.0}
        for i in range(20)
    ]
    trimmed = build_context(results, max_tokens=500)
    total_chars = sum(len(r["content"]) for r in trimmed)
    assert total_chars <= 500 * 4


def test_build_context_empty() -> None:
    assert build_context([]) == []
