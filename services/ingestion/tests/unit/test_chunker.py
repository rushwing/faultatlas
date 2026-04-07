from app.processors.chunker import chunk_text


def test_chunk_text_splits_long_text() -> None:
    text = " ".join([f"word{i}" for i in range(1000)])
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=10)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)  # some slack for overlap


def test_chunk_text_short_returns_single() -> None:
    text = "short text"
    chunks = chunk_text(text, chunk_size=512, chunk_overlap=64)
    assert len(chunks) == 1
    assert chunks[0] == "short text"
