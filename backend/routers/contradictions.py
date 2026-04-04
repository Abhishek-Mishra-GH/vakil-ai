from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from auth import get_current_user
from database.connection import get_db
from pipelines.contradiction_engine import detect_contradictions_for_case

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/cases", tags=["contradictions"])


@router.get("/{case_id}/contradictions")
async def list_contradictions(case_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    case = await db.fetchrow("SELECT id FROM cases WHERE id=$1 AND user_id=$2", case_id, current_user["id"])
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    rows = await db.fetch(
        """
        SELECT
            con.id,
            con.doc_a_id,
            doc_a.original_filename AS doc_a_name,
            con.doc_b_id,
            doc_b.original_filename AS doc_b_name,
            con.claim_a,
            con.claim_b,
            con.page_a,
            con.page_b,
            con.bbox_x0_a,
            con.bbox_y0_a,
            con.bbox_x1_a,
            con.bbox_y1_a,
            con.bbox_x0_b,
            con.bbox_y0_b,
            con.bbox_x1_b,
            con.bbox_y1_b,
            con.severity,
            con.explanation,
            con.created_at
        FROM contradictions con
        JOIN documents doc_a ON doc_a.id = con.doc_a_id
        JOIN documents doc_b ON doc_b.id = con.doc_b_id
        WHERE con.case_id=$1 AND con.user_id=$2
        ORDER BY
            CASE con.severity
                WHEN 'HIGH' THEN 1
                ELSE 2
            END,
            con.created_at DESC
        """,
        case_id,
        current_user["id"],
    )
    contradictions = [dict(row) for row in rows]
    return {
        "case_id": case_id,
        "total": len(contradictions),
        "high_count": len([row for row in contradictions if row["severity"] == "HIGH"]),
        "medium_count": len([row for row in contradictions if row["severity"] == "MEDIUM"]),
        "contradictions": contradictions,
    }


@router.post("/{case_id}/contradictions/rerun", status_code=202)
async def rerun_contradictions(
    case_id: str,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    case = await db.fetchrow("SELECT id FROM cases WHERE id=$1 AND user_id=$2", case_id, current_user["id"])
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    background_tasks.add_task(
        _run_contradictions_task,
        case_id=case_id,
        user_id=current_user["id"],
    )
    return {"status": "queued"}


async def _run_contradictions_task(case_id: str, user_id: str) -> None:
    try:
        await detect_contradictions_for_case(case_id=case_id, user_id=user_id)
    except Exception:
        logger.exception("Contradiction rerun failed: case_id=%s user_id=%s", case_id, user_id)

