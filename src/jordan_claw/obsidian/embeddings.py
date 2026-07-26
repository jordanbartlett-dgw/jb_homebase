from __future__ import annotations

import re

import logfire
from openai import AsyncOpenAI

from jordan_claw.utils.pricing import compute_embedding_cost

CHARS_PER_TOKEN = 4
MAX_CHUNK_TOKENS = 1000
OVERLAP_RATIO = 0.10
HEADING_PATTERN = re.compile(r"^#{1,3}\s", re.MULTILINE)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 512

# Cached per key so the underlying httpx connection pool is reused across calls
_embedding_clients: dict[str, AsyncOpenAI] = {}


def _get_embedding_client(api_key: str) -> AsyncOpenAI:
    client = _embedding_clients.get(api_key)
    if client is None:
        client = _embedding_clients[api_key] = AsyncOpenAI(api_key=api_key)
    return client


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def chunk_text(text: str) -> list[dict]:
    """Split text into chunks, splitting at markdown headings when over token limit.

    Returns list of dicts with keys: content, chunk_index, token_count.
    """
    if _estimate_tokens(text) <= MAX_CHUNK_TOKENS:
        return [{"content": text, "chunk_index": 0, "token_count": _estimate_tokens(text)}]

    # Split at heading boundaries
    sections: list[str] = []
    positions = [m.start() for m in HEADING_PATTERN.finditer(text)]

    if not positions:
        # No headings: split at paragraph boundaries
        paragraphs = text.split("\n\n")
        sections = [p for p in paragraphs if p.strip()]
    else:
        # Split text at each heading
        for i, pos in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            section = text[pos:end].strip()
            if section:
                sections.append(section)
        # Include any text before the first heading
        if positions[0] > 0:
            preamble = text[: positions[0]].strip()
            if preamble:
                sections.insert(0, preamble)

    # Merge small sections, split large sections
    chunks: list[str] = []
    current = ""

    for section in sections:
        candidate = (current + "\n\n" + section).strip() if current else section
        if _estimate_tokens(candidate) <= MAX_CHUNK_TOKENS:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if _estimate_tokens(section) > MAX_CHUNK_TOKENS:
                # Section itself is too large, split by paragraphs
                for para in section.split("\n\n"):
                    if not para.strip():
                        continue
                    if current and _estimate_tokens(current + "\n\n" + para) <= MAX_CHUNK_TOKENS:
                        current = current + "\n\n" + para
                    else:
                        if current:
                            chunks.append(current)
                        current = para
            else:
                current = section

    if current:
        chunks.append(current)

    if not chunks:
        return [{"content": text, "chunk_index": 0, "token_count": _estimate_tokens(text)}]

    # Add overlap between adjacent chunks
    overlap_chars = int(MAX_CHUNK_TOKENS * CHARS_PER_TOKEN * OVERLAP_RATIO)
    result: list[dict] = []

    for i, chunk in enumerate(chunks):
        if i > 0 and overlap_chars > 0:
            prev_tail = chunks[i - 1][-overlap_chars:]
            chunk = prev_tail + "\n\n" + chunk

        result.append(
            {
                "content": chunk,
                "chunk_index": i,
                "token_count": _estimate_tokens(chunk),
            }
        )

    return result


async def generate_embeddings(
    texts: list[str],
    api_key: str,
    client: AsyncOpenAI | None = None,
) -> list[list[float]]:
    """Generate embeddings for a list of texts using OpenAI API."""
    client = client or _get_embedding_client(api_key)
    with logfire.span("generate_embeddings", texts=len(texts), model=EMBEDDING_MODEL) as span:
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        # Guard response.usage.prompt_tokens with isinstance check
        # to handle both real responses and test mocks
        prompt_tokens = getattr(getattr(response, "usage", None), "prompt_tokens", None)
        if isinstance(prompt_tokens, int):
            span.set_attribute("usage.prompt_tokens", prompt_tokens)
            cost = compute_embedding_cost(EMBEDDING_MODEL, prompt_tokens)
            if cost is not None:
                span.set_attribute("usage.cost_usd", float(cost))
    # Sort by index to preserve order
    sorted_data = sorted(response.data, key=lambda d: d.index)
    return [d.embedding for d in sorted_data]
