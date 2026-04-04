from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from uuid import uuid4

from openai import AsyncOpenAI

from config import settings

_openai_client: AsyncOpenAI | None = None
logger = logging.getLogger("uvicorn.error")


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def _vector_to_pgvector_string(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.10f}" for value in values) + "]"


async def embed_chunks_batch(
    chunks: list[dict],
    batch_size: int = 20,
) -> list[dict]:
    """
    Returns chunk records with `id` and `embedding_str` for bulk insert.
    """
    if not chunks:
        return []
    logger.info("Embedding started: chunks=%s batch_size=%s", len(chunks), batch_size)
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY missing. Falling back to deterministic local embeddings")
        return _fallback_embed_chunks(chunks)

    client = _get_openai_client()
    embedded_records: list[dict] = []

    for offset in range(0, len(chunks), batch_size):
        batch = chunks[offset : offset + batch_size]
        try:
            response = await client.embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL,
                input=[chunk["content"] for chunk in batch],
            )

            for chunk, embedding_data in zip(batch, response.data):
                embedding = embedding_data.embedding
                embedded_records.append(
                    {
                        **chunk,
                        "id": str(uuid4()),
                        "embedding": embedding,
                        "embedding_str": _vector_to_pgvector_string(embedding),
                    }
                )
        except Exception as exc:
            logger.warning(
                "Embedding API batch failed at offset=%s size=%s; using fallback for this batch: %s",
                offset,
                len(batch),
                str(exc)[:220],
            )
            embedded_records.extend(_fallback_embed_chunks(batch))

        await asyncio.sleep(0.05)

    logger.info("Embedding completed: embedded_records=%s", len(embedded_records))
    return embedded_records


def _fallback_embed_chunks(chunks: list[dict]) -> list[dict]:
    records: list[dict] = []
    dim = max(8, int(settings.OPENAI_EMBEDDING_DIM))
    for chunk in chunks:
        embedding = _deterministic_embedding(str(chunk.get("content", "")), dim)
        records.append(
            {
                **chunk,
                "id": str(uuid4()),
                "embedding": embedding,
                "embedding_str": _vector_to_pgvector_string(embedding),
            }
        )
    return records


def _deterministic_embedding(text: str, dim: int) -> list[float]:
    seed = text.encode("utf-8", errors="ignore")
    values: list[float] = []
    counter = 0
    while len(values) < dim:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "little")).digest()
        counter += 1
        for idx in range(0, len(digest), 4):
            chunk = digest[idx : idx + 4]
            if len(chunk) < 4:
                continue
            number = int.from_bytes(chunk, "little")
            values.append((number / 4294967295.0) * 2.0 - 1.0)
            if len(values) >= dim:
                break
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values[:dim]]
