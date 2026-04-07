import hashlib
import math


def embed_text_locally(text: str, dimensions: int = 32) -> list[float]:
    buckets = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = digest[0] % dimensions
        buckets[index] += 1.0

    norm = math.sqrt(sum(value * value for value in buckets)) or 1.0
    return [value / norm for value in buckets]


def should_use_local_embeddings(api_key: str) -> bool:
    return api_key in {"", "test-key", "local-test-key"}
