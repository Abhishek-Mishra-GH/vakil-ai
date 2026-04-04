from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from auth import get_current_user
from database import get_db_connection, release_db_connection
from database.connection import get_db
from pipelines.brief_generator import generate_brief

router = APIRouter(prefix="/api/cases", tags=["brief"])


@router.get("/{case_id}/brief")
async def get_brief(case_id: str, db=Depends(get_db), current_user=Depends(get_current_user)): # type: ignore
    case = await db.fetchrow("SELECT id FROM cases WHERE id=$1 AND user_id=$2", case_id, current_user["id"])
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    row = await db.fetchrow(
        """
        SELECT
            case_id,
            generated_at,
            documents_used,
            core_contention,
            timeline,
            offensive_arguments,
            defensive_arguments,
            weak_points,
            key_legal_issues,
            precedents
        FROM hearing_briefs
        WHERE case_id=$1 AND user_id=$2
        """,
        case_id,
        current_user["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Brief not yet generated for this case")

    return {
        "case_id": str(row["case_id"]),
        "generated_at": row["generated_at"],
        "documents_used": row["documents_used"],
        "core_contention": row["core_contention"],
        "timeline": row["timeline"],
        "offensive_arguments": row["offensive_arguments"],
        "defensive_arguments": row["defensive_arguments"],
        "weak_points": row["weak_points"],
        "key_legal_issues": row["key_legal_issues"],
        "precedents": row["precedents"],
    }


@router.post("/{case_id}/brief/generate", status_code=202)
async def generate_case_brief(
    case_id: str,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    current_user=Depends(get_current_user), # type: ignore
):
    case = await db.fetchrow("SELECT id FROM cases WHERE id=$1 AND user_id=$2", case_id, current_user["id"])
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    background_tasks.add_task(_generate_brief_task, case_id, current_user["id"])
    return {
        "status": "generating",
        "message": "Brief generation started. Poll GET /brief for status.",
    }


async def _generate_brief_task(case_id: str, user_id: str) -> None:
    import logging

    logger = logging.getLogger("uvicorn.error")
    conn = await get_db_connection()
    try:
        await generate_brief(case_id=case_id, user_id=user_id, db=conn)
    except Exception:
        logger.exception("Brief generation failed: case_id=%s user_id=%s", case_id, user_id)
    finally:
        await release_db_connection(conn)
