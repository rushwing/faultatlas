from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_model = None
LOCAL_EMBEDDING_MODEL = os.environ.get("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        logger.info("loading local embedding model", extra={"model": LOCAL_EMBEDDING_MODEL})
        _model = TextEmbedding(LOCAL_EMBEDDING_MODEL)
        logger.info("local embedding model loaded")
    return _model


def embed_text_locally(text: str) -> list[float]:
    model = _get_model()
    # fastembed returns a generator of numpy arrays
    vectors = list(model.embed([text]))
    return vectors[0].tolist()


def should_use_local_embeddings(api_key: str) -> bool:
    return api_key in {"", "test-key", "local-test-key", "local"}
