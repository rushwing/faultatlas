from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_model = None
LOCAL_EMBEDDING_MODEL = os.environ.get("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("loading local embedding model", extra={"model": LOCAL_EMBEDDING_MODEL})
        _model = SentenceTransformer(LOCAL_EMBEDDING_MODEL)
        logger.info("local embedding model loaded")
    return _model


def embed_text_locally(text: str) -> list[float]:
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def should_use_local_embeddings(api_key: str) -> bool:
    # Treat missing, placeholder, or explicit "local" key as local-embedding mode
    return api_key in {"", "test-key", "local-test-key", "local"}
