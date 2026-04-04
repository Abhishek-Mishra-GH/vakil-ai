from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from auth import get_current_user
from config import settings
from database.connection import get_db

# from pipelines.contradiction_engine import detect_contradictions_for_case
# from pipelines.ingestion import run_ingestion_pipeline

from services.cloudinary_client import build_private_download_url, build_signed_delivery_url, delete_file, save_local_pdf_copy, upload_pdf

router = APIRouter(prefix="/api/documents", tags=["documents"])
logger = logging.getLogger("uvicorn.error")


@router.post("/upload", status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    case_id: str = Form(..., alias="case_id"),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    original_filename = Path((file.filename or "").strip()).name
    if not original_filename:
        raise HTTPException(status_code=400, detail="File name is missing")
    if not original_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    case_row = await db.fetchrow(
        "SELECT id FROM cases WHERE id=$1 AND user_id=$2",
        case_id,
        current_user["id"],
    )
    if not case_row:
        raise HTTPException(status_code=404, detail="Case not found")

    file_bytes = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit")

    try:
        upload_result = upload_pdf(
            file_bytes=file_bytes,
            folder=f"vakilai/{current_user['id']}/{case_id}",
            public_id=f"{uuid4()}_{original_filename}",
        )
    except RuntimeError as exc:
        logger.error(
            "Document upload failed before DB insert: case_id=%s user_id=%s reason=%s",
            case_id,
            current_user["id"],
            str(exc)[:200],
        )
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception(
            "Unexpected upload error before DB insert: case_id=%s user_id=%s",
            case_id,
            current_user["id"],
        )
        detail = str(exc)[:200] if settings.DEBUG else "Document upload failed"
        raise HTTPException(status_code=500, detail=detail)

    document_id = str(uuid4())
    try:
        local_file_url = save_local_pdf_copy(
            file_bytes=file_bytes,
            folder=f"vakilai/{current_user['id']}/{case_id}",
            public_id=f"{document_id}_{original_filename}",
        )
    except Exception as exc:
        logger.exception(
            "Local PDF backup failed: document_id=%s case_id=%s user_id=%s",
            document_id,
            case_id,
            current_user["id"],
        )
        detail = str(exc)[:200] if settings.DEBUG else "Could not persist local document copy"
        raise HTTPException(status_code=500, detail=detail)

    try:
        await db.execute(
            """
            INSERT INTO documents
                (id, user_id, case_id, filename, original_filename, file_url, cloudinary_public_id, processing_status)
            VALUES
                ($1, $2, $3, $4, $5, $6, $7, 'pending')
            """,
            document_id,
            current_user["id"],
            case_id,
            f"{document_id}.pdf",
            original_filename,
            local_file_url,
            upload_result.get("public_id"),
        )
    except Exception as exc:
        delete_file(upload_result.get("public_id")) # type: ignore
        logger.exception(
            "Document metadata insert failed: document_id=%s case_id=%s user_id=%s",
            document_id,
            case_id,
            current_user["id"],
        )
        detail = str(exc)[:200] if settings.DEBUG else "Could not save document metadata"
        raise HTTPException(status_code=500, detail=detail)

    return {
        "document_id": document_id,
        "status": "pending",
        "message": "Document queued for processing",
    }


@router.get("/{doc_id}/status")
async def get_document_status(doc_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    row = await db.fetchrow(
        """
        SELECT
            id,
            processing_status,
            processing_error,
            page_count,
            ocr_confidence_avg,
            detected_language,
            was_translated,
            clause_count
        FROM documents
        WHERE id=$1 AND user_id=$2
        """,
        doc_id,
        current_user["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document_id": str(row["id"]),
        "status": row["processing_status"],
        "processing_error": row["processing_error"],
        "page_count": row["page_count"],
        "ocr_confidence_avg": row["ocr_confidence_avg"],
        "detected_language": row["detected_language"],
        "was_translated": row["was_translated"],
        "clause_count": row["clause_count"],
    }


@router.get("/{doc_id}/file")
async def get_document_file(doc_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    row = await db.fetchrow(
        """
        SELECT id, original_filename, file_url, cloudinary_public_id
        FROM documents
        WHERE id=$1 AND user_id=$2
        """,
        doc_id,
        current_user["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        pdf_bytes = await _resolve_document_bytes(
            file_url=str(row["file_url"]),
            cloudinary_public_id=row["cloudinary_public_id"],
        )
    except RuntimeError as exc:
        logger.error(
            "Document file fetch failed: doc_id=%s user_id=%s reason=%s",
            doc_id,
            current_user["id"],
            str(exc)[:240],
        )
        raise HTTPException(status_code=502, detail=str(exc))

    filename = Path(str(row["original_filename"] or "document.pdf")).name or "document.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    row = await db.fetchrow(
        """
        SELECT id, case_id, cloudinary_public_id
        FROM documents
        WHERE id=$1 AND user_id=$2
        """,
        doc_id,
        current_user["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.execute("DELETE FROM documents WHERE id=$1 AND user_id=$2", doc_id, current_user["id"])
    delete_file(row["cloudinary_public_id"])
    return {"status": "deleted"}


@router.get("")
async def list_documents(db=Depends(get_db), current_user=Depends(get_current_user)):
    rows = await db.fetch(
        """
        SELECT
            id,
            case_id,
            original_filename,
            processing_status,
            page_count,
            clause_count,
            ocr_confidence_avg,
            detected_language,
            was_translated,
            created_at
        FROM documents
        WHERE user_id=$1
        ORDER BY created_at DESC
        """,
        current_user["id"],
    )
    return {"documents": [dict(row) for row in rows]}


async def _resolve_document_bytes(file_url: str, cloudinary_public_id: str | None) -> bytes:
    parsed = urlparse(file_url)
    if parsed.scheme == "file":
        path_str = unquote(parsed.path or "")
        if len(path_str) >= 3 and path_str[0] == "/" and path_str[2] == ":":
            path_str = path_str[1:]
        try:
            with open(path_str, "rb") as handle:
                content = handle.read()
        except Exception as exc:
            raise RuntimeError(f"Could not open local PDF file: {str(exc)[:180]}") from exc
        if not content:
            raise RuntimeError("Local PDF file is empty")
        return content

    candidates: list[str] = []
    private_download_url = build_private_download_url(cloudinary_public_id)
    if private_download_url:
        candidates.append(private_download_url)
    original_format_download_url = build_private_download_url(cloudinary_public_id, file_format=None)
    if original_format_download_url and original_format_download_url not in candidates:
        candidates.append(original_format_download_url)
    signed_url = build_signed_delivery_url(cloudinary_public_id)
    if signed_url:
        candidates.append(signed_url)
    if file_url not in candidates:
        candidates.append(file_url)

    attempts: list[str] = []
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        for candidate_url in candidates:
            try:
                response = await client.get(candidate_url)
            except Exception as exc:
                attempts.append(f"{candidate_url} -> request failed: {str(exc)[:120]}")
                continue

            if response.status_code >= 400:
                attempts.append(f"{candidate_url} -> HTTP {response.status_code}")
                continue
            content = response.content
            if not content:
                attempts.append(f"{candidate_url} -> empty response body")
                continue
            content_type = (response.headers.get("content-type") or "").lower()
            if "pdf" not in content_type and not content.startswith(b"%PDF"):
                attempts.append(f"{candidate_url} -> non-PDF content-type={content_type or 'unknown'}")
                continue
            return content

    failure = "; ".join(attempts[:3]) if attempts else "No candidate URLs available"
    raise RuntimeError(f"Could not fetch document PDF. {failure}")
