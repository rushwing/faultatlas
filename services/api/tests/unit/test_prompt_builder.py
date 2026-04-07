from services.api.app.agents.prompt_builder import build_diagnosis_prompt


def test_prompt_builder_is_stable() -> None:
    chunks = [
        {"chunk_id": "b", "document_id": "doc-1", "content": "beta", "score": 0.8},
        {"chunk_id": "a", "document_id": "doc-1", "content": "alpha", "score": 0.8},
    ]
    prompt = build_diagnosis_prompt("query", chunks)
    assert prompt.layer1_hash
    assert prompt.chunk_ids == ["a", "b"]
    assert "## Retrieved Evidence" in prompt.layer2_text
    assert "## Incident Description" in prompt.layer3_text
