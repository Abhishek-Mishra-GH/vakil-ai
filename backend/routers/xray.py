from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from database.connection import get_db

router = APIRouter(prefix="/api/xray", tags=["xray"])


@router.get("/{doc_id}/insights")
async def get_insights(doc_id: str, db=Depends(get_db), current_user=Depends(get_current_user)): # type: ignore
    doc = await db.fetchrow(
        "SELECT id FROM documents WHERE id=$1 AND user_id=$2",
        doc_id,
        current_user["id"],
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    rows = await db.fetch(
        """
        SELECT
            id,
            clause_type,
            summary,
            anomaly_flag,
            anomaly_reason,
            statutory_reference,
            statutory_id,
            page_number,
            bbox_x0,
            bbox_y0,
            bbox_x1,
            bbox_y1
        FROM insights
        WHERE document_id=$1
        ORDER BY
            CASE anomaly_flag
                WHEN 'HIGH_RISK' THEN 1
                WHEN 'MEDIUM_RISK' THEN 2
                ELSE 3
            END,
            page_number ASC
        """,
        doc_id,
    )
    total = len(rows)
    high_risk = len([row for row in rows if row["anomaly_flag"] == "HIGH_RISK"])
    medium_risk = len([row for row in rows if row["anomaly_flag"] == "MEDIUM_RISK"])
    standard = len([row for row in rows if row["anomaly_flag"] == "STANDARD"])
    return {
        "document_id": doc_id,
        "total_clauses": total,
        "high_risk_count": high_risk,
        "medium_risk_count": medium_risk,
        "standard_count": standard,
        "insights": [dict(row) for row in rows],
    }

