from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from auth import get_current_user
from database.connection import get_db

router = APIRouter(prefix="/api/cases", tags=["cases"])


class CaseCreateRequest(BaseModel):
    title: str
    case_number: str | None = None
    court_name: str | None = None
    court_number: str | None = None
    opposing_party: str | None = None
    hearing_date: datetime | None = None
    hearing_time: str | None = None
    status: str | None = "active"
    notes: str | None = None

    @field_validator("hearing_date", mode="before")
    @classmethod
    def normalize_hearing_date(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class CasePatchRequest(BaseModel):
    title: str | None = None
    case_number: str | None = None
    court_name: str | None = None
    court_number: str | None = None
    opposing_party: str | None = None
    hearing_date: datetime | None = None
    hearing_time: str | None = None
    status: str | None = None
    notes: str | None = None

    @field_validator("hearing_date", mode="before")
    @classmethod
    def normalize_hearing_date(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


@router.get("")
async def list_cases(db=Depends(get_db), current_user=Depends(get_current_user)):
    rows = await db.fetch(
        """
        SELECT
            c.id,
            c.title,
            c.case_number,
            c.court_name,
            c.hearing_date,
            c.status,
            c.created_at,
            COUNT(DISTINCT d.id) AS document_count,
            COUNT(DISTINCT d.id) FILTER (WHERE d.processing_status='ready') AS ready_document_count,
            COUNT(DISTINCT con.id) AS contradiction_count,
            (hb.id IS NOT NULL) AS has_brief
        FROM cases c
        LEFT JOIN documents d ON d.case_id = c.id AND d.user_id = c.user_id
        LEFT JOIN contradictions con ON con.case_id = c.id AND con.user_id = c.user_id
        LEFT JOIN hearing_briefs hb ON hb.case_id = c.id AND hb.user_id = c.user_id
        WHERE c.user_id = $1
        GROUP BY c.id, hb.id
        ORDER BY c.hearing_date ASC NULLS LAST, c.created_at DESC
        """,
        current_user["id"],
    )
    return {"cases": [dict(row) for row in rows]}


@router.post("", status_code=201)
async def create_case(payload: CaseCreateRequest, db=Depends(get_db), current_user=Depends(get_current_user)):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Case title is required")

    case_id = str(uuid4())
    await db.execute(
        """
        INSERT INTO cases
            (id, user_id, title, case_number, court_name, court_number,
             opposing_party, hearing_date, hearing_time, status, notes)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7,
             $8::timestamptz, $9, $10, $11)
        """,
        case_id,
        current_user["id"],
        title,
        payload.case_number,
        payload.court_name,
        payload.court_number,
        payload.opposing_party,
        payload.hearing_date,
        payload.hearing_time,
        payload.status or "active",
        payload.notes,
    )

    created = await db.fetchrow("SELECT * FROM cases WHERE id=$1", case_id)
    return dict(created)


@router.get("/{case_id}")
async def get_case(case_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    case = await _get_owned_case(db, case_id, current_user["id"])
    documents = await db.fetch(
        """
        SELECT
            id,
            original_filename,
            processing_status,
            processing_error,
            page_count,
            clause_count,
            ocr_confidence_avg,
            detected_language,
            was_translated,
            created_at
        FROM documents
        WHERE case_id=$1 AND user_id=$2
        ORDER BY created_at DESC
        """,
        case_id,
        current_user["id"],
    )
    counts = await db.fetchrow(
        """
        SELECT
            COUNT(*) AS document_count,
            COUNT(*) FILTER (WHERE processing_status='ready') AS ready_document_count
        FROM documents
        WHERE case_id=$1 AND user_id=$2
        """,
        case_id,
        current_user["id"],
    )
    contradiction_count = await db.fetchval(
        "SELECT COUNT(*) FROM contradictions WHERE case_id=$1 AND user_id=$2",
        case_id,
        current_user["id"],
    )
    has_brief = await db.fetchval(
        "SELECT EXISTS(SELECT 1 FROM hearing_briefs WHERE case_id=$1 AND user_id=$2)",
        case_id,
        current_user["id"],
    )
    result = dict(case)
    result.update(
        {
            "document_count": counts["document_count"],
            "ready_document_count": counts["ready_document_count"],
            "contradiction_count": contradiction_count,
            "has_brief": has_brief,
            "documents": [dict(document) for document in documents],
        }
    )
    return result


@router.patch("/{case_id}")
async def update_case(
    case_id: str,
    payload: CasePatchRequest,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_owned_case(db, case_id, current_user["id"])
    update_fields = payload.model_dump(exclude_unset=True)
    if not update_fields:
        return dict(await _get_owned_case(db, case_id, current_user["id"]))

    allowed = {
        "title",
        "case_number",
        "court_name",
        "court_number",
        "opposing_party",
        "hearing_date",
        "hearing_time",
        "status",
        "notes",
    }
    clauses = []
    values: list[Any] = []
    idx = 1
    for key, value in update_fields.items():
        if key not in allowed:
            continue
        if key == "hearing_date":
            clauses.append(f"{key} = ${idx}::timestamptz")
        else:
            clauses.append(f"{key} = ${idx}")
        values.append(value)
        idx += 1
    if not clauses:
        return dict(await _get_owned_case(db, case_id, current_user["id"]))

    values.extend([case_id, current_user["id"]])
    await db.execute(
        f"""
        UPDATE cases
        SET {', '.join(clauses)}, updated_at=NOW()
        WHERE id=${idx} AND user_id=${idx + 1}
        """,
        *values,
    )
    return dict(await _get_owned_case(db, case_id, current_user["id"]))


@router.delete("/{case_id}")
async def delete_case(case_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    await _get_owned_case(db, case_id, current_user["id"])
    await db.execute("DELETE FROM cases WHERE id=$1 AND user_id=$2", case_id, current_user["id"])
    return {"status": "deleted"}


@router.get("/{case_id}/documents")
async def list_case_documents(case_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    await _get_owned_case(db, case_id, current_user["id"])
    rows = await db.fetch(
        """
        SELECT
            id,
            original_filename,
            processing_status,
            processing_error,
            page_count,
            clause_count,
            ocr_confidence_avg,
            detected_language,
            was_translated,
            file_url,
            created_at
        FROM documents
        WHERE case_id=$1 AND user_id=$2
        ORDER BY created_at DESC
        """,
        case_id,
        current_user["id"],
    )
    return {"documents": [dict(row) for row in rows]}


@router.get("/{case_id}/document-suggestions")
async def suggest_documents(case_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    await _get_owned_case(db, case_id, current_user["id"])
    docs = await db.fetch(
        """
        SELECT original_filename, processing_status
        FROM documents
        WHERE case_id=$1 AND user_id=$2
        ORDER BY created_at ASC
        """,
        case_id,
        current_user["id"],
    )
    contradiction_high = await db.fetchval(
        """
        SELECT COUNT(*)
        FROM contradictions
        WHERE case_id=$1 AND user_id=$2 AND severity='HIGH'
        """,
        case_id,
        current_user["id"],
    )
    has_brief = await db.fetchval(
        "SELECT EXISTS(SELECT 1 FROM hearing_briefs WHERE case_id=$1 AND user_id=$2)",
        case_id,
        current_user["id"],
    )

    ready_docs = [row for row in docs if row["processing_status"] == "ready"]
    titles = [str(row["original_filename"]).lower() for row in docs]
    suggestions: list[dict[str, str]] = []

    def add(kind: str, why: str, template: str):
        suggestions.append({"document_type": kind, "why_needed": why, "starter_template": template})

    if len(docs) == 0:
        add(
            "Core pleadings set",
            "No case documents uploaded yet.",
            "1) Case title and parties\n2) Relief sought\n3) Key dates and facts\n4) Prayer clause",
        )
    if len(ready_docs) < 2:
        add(
            "Opposing side pleading/reply",
            "Contradiction engine and stronger argument mapping need at least two ready documents.",
            "1) Reply heading\n2) Para-wise response\n3) Supporting annexures list\n4) Verification",
        )
    if not any("timeline" in title or "chronology" in title for title in titles):
        add(
            "Chronology chart",
            "Hearing briefs and cross-examination are stronger with a one-page timeline.",
            "Date | Event | Source document/page | Legal relevance",
        )
    if contradiction_high and contradiction_high > 0:
        add(
            "Reconciliation affidavit",
            "High-severity contradictions were detected and should be proactively addressed.",
            "1) Contradiction identified\n2) Correct factual position\n3) Documentary basis\n4) Clarificatory prayer",
        )
    if not has_brief:
        add(
            "Pre-flight hearing note",
            "No generated hearing brief exists for this case.",
            "Issue | Your position | Opponent likely attack | Citation | Oral submission line",
        )

    if not suggestions:
        add(
            "Additional supporting exhibits",
            "Case file appears complete; add focused exhibits for each key issue before hearing.",
            "Exhibit no. | Fact proved | Source origin | Admissibility note",
        )

    return {"case_id": case_id, "suggestions": suggestions}


async def _get_owned_case(db, case_id: str, user_id: str):
    row = await db.fetchrow("SELECT * FROM cases WHERE id=$1 AND user_id=$2", case_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return row
