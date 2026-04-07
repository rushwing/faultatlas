def build_context(results: list[dict], max_tokens: int = 3000) -> list[dict]:
    """Trim results to stay within a rough token budget (1 token ≈ 4 chars)."""
    budget = max_tokens * 4
    selected = []
    used = 0
    for r in sorted(results, key=lambda item: (-item["score"], item["chunk_id"])):
        length = len(r["content"])
        if used + length > budget:
            break
        selected.append(r)
        used += length
    return selected
