import hashlib
from dataclasses import dataclass

from .prompts import CONTROL_SYSTEM_PROMPT, DIAGNOSIS_OUTPUT_SCHEMA, PROMPT_VERSION, SYSTEM_PROMPT


@dataclass
class PromptBundle:
    messages: list[dict[str, str]]
    prompt_version: str
    layer1_text: str
    layer2_text: str
    layer3_text: str
    layer1_hash: str
    layer2_hash: str
    chunk_ids: list[str]
    total_estimated_tokens: int


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _estimate_tokens(text: str) -> int:
    return max(len(text) // 4, 1)


def _build_system_prompt(variant: str) -> str:
    template = SYSTEM_PROMPT if variant == "default" else CONTROL_SYSTEM_PROMPT
    return template.format(schema=DIAGNOSIS_OUTPUT_SCHEMA)


def build_diagnosis_prompt(
    query: str,
    chunks: list[dict],
    *,
    variant: str = "default",
) -> PromptBundle:
    ordered_chunks = sorted(chunks, key=lambda item: (-item["score"], item["chunk_id"]))
    chunk_lines = []
    chunk_ids = []
    for chunk in ordered_chunks:
        chunk_ids.append(chunk["chunk_id"])
        chunk_lines.append(
            "[chunk_id={chunk_id} document_id={document_id} score={score:.3f}]\n{content}".format(
                chunk_id=chunk["chunk_id"],
                document_id=chunk["document_id"],
                score=chunk["score"],
                content=chunk["content"],
            )
        )

    layer1_text = _build_system_prompt(variant)
    layer2_text = "## Retrieved Evidence\n" + (
        "\n\n---\n\n".join(chunk_lines) if chunk_lines else "No evidence retrieved."
    )
    layer3_text = f"## Incident Description\n{query}"
    messages = [
        {"role": "system", "content": layer1_text},
        {"role": "user", "content": f"{layer2_text}\n\n{layer3_text}"},
    ]
    total_estimated_tokens = (
        _estimate_tokens(layer1_text)
        + _estimate_tokens(layer2_text)
        + _estimate_tokens(layer3_text)
    )
    return PromptBundle(
        messages=messages,
        prompt_version=PROMPT_VERSION,
        layer1_text=layer1_text,
        layer2_text=layer2_text,
        layer3_text=layer3_text,
        layer1_hash=_sha256(layer1_text),
        layer2_hash=_sha256(layer2_text),
        chunk_ids=chunk_ids,
        total_estimated_tokens=total_estimated_tokens,
    )
