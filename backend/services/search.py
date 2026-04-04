from __future__ import annotations

import json
from typing import Any

import asyncpg
import cohere
from openai import AsyncOpenAI

from config import settings

_openai_client: AsyncOpenAI | None = None
_cohere_client: cohere.AsyncClient | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def _get_cohere_client() -> cohere.AsyncClient | None:
    global _cohere_client
    if not settings.COHERE_API_KEY:
        return None
    if _cohere_client is None:
        _cohere_client = cohere.AsyncClient(api_key=settings.COHERE_API_KEY)
    return _cohere_client


async def hybrid_search(
    query: str,
    case_id: str,
    user_id: str,
    db: asyncpg.Connection,
    document_id: str | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    if not settings.OPENAI_API_KEY:
        return await _fts_only_search(query, case_id, user_id, db, document_id, top_k)

    client = _get_openai_client()
    embedding_response = await client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=query,
    )
    query_vector = embedding_response.data[0].embedding
    vector_str = "[" + ",".join(str(x) for x in query_vector) + "]"

    base_filter = "case_id = $2 AND user_id = $3"
    params: list[Any] = [vector_str, case_id, user_id]
    query_arg = [query, case_id, user_id]
    doc_filter = ""
    if document_id:
        doc_filter = " AND document_id = $4"
        params.append(document_id)
        query_arg.append(document_id)

    vector_rows = await db.fetch(
        f"""
        SELECT
            id, document_id, content, page_number, section_header,
            bbox_x0, bbox_y0, bbox_x1, bbox_y1,
            1 - (embedding <=> $1::vector) AS vector_score
        FROM chunks
        WHERE {base_filter}
          {doc_filter}
          AND embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT 15
        """,
        *params,
    )

    bm25_rows = await db.fetch(
        f"""
        SELECT
            id, document_id, content, page_number, section_header,
            bbox_x0, bbox_y0, bbox_x1, bbox_y1,
            ts_rank_cd(
                to_tsvector('english', content),
                plainto_tsquery('english', $1)
            ) AS bm25_score
        FROM chunks
        WHERE case_id = $2
          AND user_id = $3
          {doc_filter}
          AND to_tsvector('english', content) @@ plainto_tsquery('english', $1)
        ORDER BY bm25_score DESC
        LIMIT 15
        """,
        *query_arg,
    )

    combined: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in list(vector_rows) + list(bm25_rows):
        row_dict = dict(row)
        row_id = str(row_dict["id"])
        if row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        combined.append(row_dict)

    if not combined:
        return []
    if len(combined) == 1:
        return combined

    cohere_client = _get_cohere_client()
    if cohere_client is None:
        combined.sort(key=lambda item: item.get("vector_score", item.get("bm25_score", 0)), reverse=True)
        return combined[:top_k]

    try:
        rerank_response = await cohere_client.rerank(
            model=settings.COHERE_RERANK_MODEL,
            query=query,
            documents=[item["content"] for item in combined],
            top_n=min(top_k, len(combined)),
        )
        reranked: list[dict[str, Any]] = []
        for rerank_item in rerank_response.results:
            chunk = combined[rerank_item.index]
            chunk["rerank_score"] = rerank_item.relevance_score
            reranked.append(chunk)
        return reranked
    except Exception:
        combined.sort(key=lambda item: item.get("vector_score", item.get("bm25_score", 0)), reverse=True)
        return combined[:top_k]


async def _fts_only_search(
    query: str,
    case_id: str,
    user_id: str,
    db: asyncpg.Connection,
    document_id: str | None,
    top_k: int,
) -> list[dict[str, Any]]:
    params: list[Any] = [query, case_id, user_id]
    doc_filter = ""
    if document_id:
        doc_filter = " AND document_id = $4"
        params.append(document_id)
    rows = await db.fetch(
        f"""
        SELECT
            id, document_id, content, page_number, section_header,
            bbox_x0, bbox_y0, bbox_x1, bbox_y1,
            ts_rank_cd(
                to_tsvector('english', content),
                plainto_tsquery('english', $1)
            ) AS bm25_score
        FROM chunks
        WHERE case_id = $2
          AND user_id = $3
          {doc_filter}
          AND to_tsvector('english', content) @@ plainto_tsquery('english', $1)
        ORDER BY bm25_score DESC
        LIMIT $5
        """,
        *params,
        top_k,
    )
    return [dict(row) for row in rows]


def search_statutes_in_memory(query: str, statutes_path: str, limit: int = 10) -> list[dict[str, Any]]:
    with open(statutes_path, "r", encoding="utf-8") as handle:
        statutes = json.load(handle)
    q = query.lower().strip()
    scored: list[tuple[int, dict[str, Any]]] = []
    for statute in statutes:
        haystack = " ".join(
            [
                str(statute.get("act", "")),
                str(statute.get("section", "")),
                str(statute.get("title", "")),
                str(statute.get("summary", "")),
                " ".join(statute.get("keywords", [])),
            ]
        ).lower()
        score = haystack.count(q) if q and q in haystack else 0
        if score > 0:
            scored.append((score, statute))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]

