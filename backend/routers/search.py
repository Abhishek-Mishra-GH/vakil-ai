from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from auth import get_current_user
from config import settings
from database.connection import get_db
from services.indian_kanoon import fetch_precedents
from services.search import hybrid_search, search_statutes_in_memory

router = APIRouter(prefix="/api/search", tags=["search"])


class HybridSearchRequest(BaseModel):
    query: str
    case_id: str
    document_id: str | None = None
    top_k: int = 5

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Query is required")
        return text


@router.post("/hybrid")
async def hybrid_search_endpoint(
    payload: HybridSearchRequest,
    db=Depends(get_db),
    current_user=Depends(get_current_user), # type: ignore
):
    case = await db.fetchrow(
        "SELECT id FROM cases WHERE id=$1 AND user_id=$2",
        payload.case_id,
        current_user["id"],
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    results = await hybrid_search(
        query=payload.query,
        case_id=payload.case_id,
        user_id=current_user["id"],
        db=db,
        document_id=payload.document_id,
        top_k=max(1, min(payload.top_k, 20)),
    )
    return {"query": payload.query, "results": results}


@router.get("/statutes")
async def statutes_search(
    query: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    current_user=Depends(get_current_user), # type: ignore
):
    results = search_statutes_in_memory(query=query, statutes_path=str(settings.statutes_path), limit=limit)
    return {"query": query, "results": results}


@router.get("/precedents")
async def precedents_search(
    query: str = Query(..., min_length=2),
    limit: int = Query(3, ge=1, le=10),
    current_user=Depends(get_current_user), # type: ignore
):
    try:
        results = await fetch_precedents(legal_issue=query, max_results=limit)
        return {"query": query, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
