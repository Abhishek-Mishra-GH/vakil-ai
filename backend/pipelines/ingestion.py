from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from langdetect import LangDetectException, detect

from config import settings
from database import get_db_connection, release_db_connection
from pipelines.chunker import create_legal_chunks
from pipelines.embedder import embed_chunks_batch
from pipelines.textract_parser import parse_textract_blocks, run_textract
from pipelines.xray_analyzer import analyze_chunks_for_insights
from services.translation import translate_pages

logger = logging.getLogger("uvicorn.error")


async def run_ingestion_pipeline(
    doc_id: str,
    case_id: str,
    user_id: str,
    file_url: str,
    file_bytes: bytes | None = None,
) -> None:
    started_at = perf_counter()
    logger.info(
        "Ingestion started: doc_id=%s case_id=%s user_id=%s file_url_scheme=%s",
        doc_id,
        case_id,
        user_id,
        (urlparse(file_url).scheme or "unknown"),
    )
    conn = await get_db_connection()
    try:
        if file_bytes is None:
            download_start = perf_counter()
            pdf_bytes = await _load_pdf_bytes(file_url)
            logger.info(
                "Ingestion download complete: doc_id=%s bytes=%s duration=%.2fs",
                doc_id,
                len(pdf_bytes),
                perf_counter() - download_start,
            )
        else:
            pdf_bytes = file_bytes
            logger.info("Ingestion using in-memory upload bytes: doc_id=%s bytes=%s", doc_id, len(pdf_bytes))

        await _set_status(conn, doc_id, "ocr_running")
        ocr_start = perf_counter()
        textract_response = await asyncio.to_thread(run_textract, pdf_bytes)
        
        if textract_response is None:
            await _fail(conn, doc_id, "OCR failed: No valid response from any OCR method")
            return
        
        ocr_source = str(textract_response.get("_source", "textract"))

        line_blocks = [block for block in textract_response.get("Blocks", []) if block.get("BlockType") == "LINE"]
        logger.info(
            "OCR completed: doc_id=%s source=%s line_blocks=%s duration=%.2fs",
            doc_id,
            ocr_source,
            len(line_blocks),
            perf_counter() - ocr_start,
        )
        if not line_blocks:
            await _fail(conn, doc_id, "No text detected in document")
            return

        avg_confidence = sum(float(block.get("Confidence", 0.0)) for block in line_blocks) / len(line_blocks)
        await conn.execute(
            "UPDATE documents SET ocr_confidence_avg=$1 WHERE id=$2",
            avg_confidence,
            doc_id,
        )
        logger.info("OCR confidence: doc_id=%s avg_confidence=%.2f", doc_id, avg_confidence)
        if avg_confidence < settings.OCR_CONFIDENCE_THRESHOLD:
            await _fail(
                conn,
                doc_id,
                (
                    f"Illegible scan detected. OCR confidence {avg_confidence:.1f}% "
                    f"is below threshold {settings.OCR_CONFIDENCE_THRESHOLD:.1f}%."
                ),
            )
            return

        pages = parse_textract_blocks(textract_response)
        page_count = len(pages)
        await conn.execute("UPDATE documents SET page_count=$1 WHERE id=$2", page_count, doc_id)
        logger.info("Parsed OCR pages: doc_id=%s pages=%s", doc_id, page_count)

        sample_text = " ".join(page.get("text", "")[:500] for page in pages[:3])
        try:
            detected_language = detect(sample_text) if sample_text.strip() else "en"
        except LangDetectException:
            detected_language = "en"
        logger.info("Language detection: doc_id=%s lang=%s", doc_id, detected_language)

        was_translated = False
        if detected_language != "en":
            logger.info("Translation started: doc_id=%s source_lang=%s", doc_id, detected_language)
            translated_pages = await translate_pages(pages, detected_language)
            if translated_pages != pages:
                pages = translated_pages
                was_translated = True
            logger.info("Translation finished: doc_id=%s translated=%s", doc_id, was_translated)

        await conn.execute(
            """
            UPDATE documents
            SET detected_language=$1, was_translated=$2
            WHERE id=$3
            """,
            detected_language,
            was_translated,
            doc_id,
        )

        await _set_status(conn, doc_id, "chunking")
        chunk_start = perf_counter()
        chunks = create_legal_chunks(pages)
        if not chunks:
            await _fail(conn, doc_id, "Could not extract semantic chunks from document")
            return
        logger.info(
            "Chunking completed: doc_id=%s chunks=%s duration=%.2fs",
            doc_id,
            len(chunks),
            perf_counter() - chunk_start,
        )

        await _set_status(conn, doc_id, "embedding")
        embedding_start = perf_counter()
        embedded_chunks = await embed_chunks_batch(chunks)
        await conn.executemany(
            """
            INSERT INTO chunks
                (id, document_id, case_id, user_id, content, content_original,
                 page_number, bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                 chunk_index, section_header, embedding)
            VALUES
                ($1, $2, $3, $4, $5, $6, $7,
                 $8, $9, $10, $11, $12, $13, $14)
            """,
            [
                (
                    chunk["id"],
                    doc_id,
                    case_id,
                    user_id,
                    chunk["content"],
                    chunk.get("content_original"),
                    chunk["page_number"],
                    float(chunk["bbox"]["x0"]),
                    float(chunk["bbox"]["y0"]),
                    float(chunk["bbox"]["x1"]),
                    float(chunk["bbox"]["y1"]),
                    chunk["chunk_index"],
                    chunk.get("section_header"),
                    chunk["embedding_str"],
                )
                for chunk in embedded_chunks
            ],
        )
        logger.info(
            "Embedding + chunk insert completed: doc_id=%s embedded_chunks=%s duration=%.2fs",
            doc_id,
            len(embedded_chunks),
            perf_counter() - embedding_start,
        )

        await _set_status(conn, doc_id, "analyzing")
        analysis_start = perf_counter()
        insight_count = await analyze_chunks_for_insights(
            chunks=embedded_chunks,
            doc_id=doc_id,
            case_id=case_id,
            user_id=user_id,
            db=conn,
        )
        await conn.execute(
            "UPDATE documents SET clause_count=$1 WHERE id=$2",
            insight_count,
            doc_id,
        )
        logger.info(
            "XRay analysis completed: doc_id=%s insights=%s duration=%.2fs",
            doc_id,
            insight_count,
            perf_counter() - analysis_start,
        )

        await _set_status(conn, doc_id, "ready")
        logger.info(
            "Ingestion ready: doc_id=%s case_id=%s total_duration=%.2fs",
            doc_id,
            case_id,
            perf_counter() - started_at,
        )
        # asyncio.create_task(detect_contradictions_for_case(case_id=case_id, user_id=user_id))
    except Exception as exc:  # pragma: no cover - runtime errors from services
        logger.exception("Ingestion failed: doc_id=%s case_id=%s user_id=%s", doc_id, case_id, user_id)
        try:
            await _fail(conn, doc_id, f"Internal processing error: {str(exc)[:200]}")
        except Exception:
            logger.exception("Failed to persist ingestion failure state: doc_id=%s", doc_id)
    finally:
        await release_db_connection(conn)


async def _load_pdf_bytes(file_url: str) -> bytes:
    parsed = urlparse(file_url)
    if parsed.scheme == "file":
        path_str = unquote(parsed.path or "")
        # Windows file URIs often begin with /C:/..., strip only that extra slash.
        if len(path_str) >= 3 and path_str[0] == "/" and path_str[2] == ":":
            path_str = path_str[1:]
        with open(path_str, "rb") as handle:
            content = handle.read()
        if not content:
            raise RuntimeError(f"Local file is empty: {path_str}")
        return content
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        response = await client.get(file_url)
        response.raise_for_status()
    content = response.content
    if not content:
        raise RuntimeError("Downloaded file is empty")
    content_type = (response.headers.get("content-type") or "").lower()
    if "pdf" not in content_type and not content.startswith(b"%PDF"):
        raise RuntimeError(f"Downloaded file is not a PDF (content-type={content_type or 'unknown'})")
    return content


async def _set_status(conn, doc_id: str, status: str) -> None:
    await conn.execute(
        """
        UPDATE documents
        SET processing_status=$1, processing_error=NULL, updated_at=NOW()
        WHERE id=$2
        """,
        status,
        doc_id,
    )
    logger.info("Ingestion status update: doc_id=%s status=%s", doc_id, status)


async def _fail(conn, doc_id: str, error_message: str) -> None:
    logger.error("Ingestion status update: doc_id=%s status=failed reason=%s", doc_id, error_message)
    await conn.execute(
        """
        UPDATE documents
        SET processing_status='failed',
            processing_error=$1,
            updated_at=NOW()
        WHERE id=$2
        """,
        error_message,
        doc_id,
    )
