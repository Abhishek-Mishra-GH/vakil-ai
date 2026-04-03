from __future__ import annotations

from io import BytesIO
import logging
from typing import Any

import boto3

from config import settings

logger = logging.getLogger("uvicorn.error")


def _textract_client():
    client_kwargs: dict[str, Any] = {"region_name": settings.AWS_REGION}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        client_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        client_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client("textract", **client_kwargs)


def run_textract(pdf_bytes: bytes) -> dict[str, Any]:
    """
    Best-effort OCR:
    - First attempts multipage OCR via pdf2image + analyze_document per page.
    - Falls back to direct analyze_document for simple/single page files.
    """
    pages = run_textract_multipage(pdf_bytes)
    if pages:
        logger.info("OCR source=textract_multipage pages=%s", len(pages))
        return {"Blocks": _pages_to_blocks(pages), "_source": "textract_multipage"}

    try:
        client = _textract_client()
        response = client.analyze_document(
            Document={"Bytes": pdf_bytes},
            FeatureTypes=["LAYOUT", "TABLES"],
        )
        line_count = len([block for block in response.get("Blocks", []) if block.get("BlockType") == "LINE"])
        if line_count == 0:
            logger.warning("Textract direct returned no LINE blocks; trying pypdf fallback")
            fallback_pages = _extract_text_with_pypdf(pdf_bytes)
            if fallback_pages:
                logger.warning("OCR fallback source=pypdf pages=%s", len(fallback_pages))
                return {"Blocks": _pages_to_blocks(fallback_pages), "_source": "pypdf_fallback"}
        response["_source"] = "textract_direct"
        logger.info("OCR source=textract_direct blocks=%s", len(response.get("Blocks", [])))
        return response
    except Exception as exc:
        logger.warning("Textract direct analyze_document failed: %s", str(exc)[:240])

    fallback_pages = _extract_text_with_pypdf(pdf_bytes)
    if fallback_pages:
        logger.warning("OCR fallback source=pypdf pages=%s", len(fallback_pages))
        return {"Blocks": _pages_to_blocks(fallback_pages), "_source": "pypdf_fallback"}

    raise RuntimeError(
        "OCR failed. Check AWS Textract credentials/permissions or install pdf2image+poppler. "
        "For text PDFs, install pypdf as fallback."
    )


def run_textract_multipage(pdf_bytes: bytes) -> list[dict[str, Any]]:
    try:
        from pdf2image import convert_from_bytes  # type: ignore
    except Exception:
        logger.info("pdf2image not available; skipping Textract multipage OCR path")
        return []
    try:
        images = convert_from_bytes(pdf_bytes, dpi=200)
    except Exception as exc:
        logger.info("pdf2image conversion unavailable, falling back from multipage OCR: %s", str(exc)[:220])
        return []

    client = _textract_client()
    pages: list[dict[str, Any]] = []

    for page_index, image in enumerate(images, start=1):
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        try:
            response = client.analyze_document(
                Document={"Bytes": buffer.getvalue()},
                FeatureTypes=["LAYOUT", "TABLES"],
            )
            parsed = parse_textract_blocks(response)
            for page in parsed:
                page["page"] = page_index
            pages.extend(parsed)
        except Exception as exc:
            logger.warning("Textract multipage OCR failed on page %s: %s", page_index, str(exc)[:220])

    return pages


def parse_textract_blocks(response: dict[str, Any]) -> list[dict[str, Any]]:
    pages: dict[int, dict[str, Any]] = {}

    for block in response.get("Blocks", []):
        if block.get("BlockType") != "LINE":
            continue
        page_num = int(block.get("Page", 1))
        page = pages.setdefault(page_num, {"page": page_num, "lines": [], "text": ""})

        raw_bbox = block.get("Geometry", {}).get("BoundingBox", {})
        x0 = float(raw_bbox.get("Left", 0.0))
        y0 = float(raw_bbox.get("Top", 0.0))
        width = float(raw_bbox.get("Width", 0.0))
        height = float(raw_bbox.get("Height", 0.0))
        line_obj = {
            "text": block.get("Text", ""),
            "confidence": float(block.get("Confidence", 0.0)),
            "page": page_num,
            "bbox": {
                "x0": x0,
                "y0": y0,
                "x1": x0 + width,
                "y1": y0 + height,
            },
        }
        page["lines"].append(line_obj)

    parsed_pages: list[dict[str, Any]] = []
    for page_num in sorted(pages):
        page = pages[page_num]
        page["text"] = "\n".join(line["text"] for line in page["lines"])
        parsed_pages.append(page)
    return parsed_pages


def _pages_to_blocks(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for page in pages:
        page_num = int(page.get("page", 1))
        for line in page.get("lines", []):
            bbox = line.get("bbox", {})
            blocks.append(
                {
                    "BlockType": "LINE",
                    "Page": page_num,
                    "Text": line.get("text", ""),
                    "Confidence": line.get("confidence", 0.0),
                    "Geometry": {
                        "BoundingBox": {
                            "Left": float(bbox.get("x0", 0.0)),
                            "Top": float(bbox.get("y0", 0.0)),
                            "Width": float(bbox.get("x1", 1.0)) - float(bbox.get("x0", 0.0)),
                            "Height": float(bbox.get("y1", 1.0)) - float(bbox.get("y0", 0.0)),
                        }
                    },
                }
            )
    return blocks


def _extract_text_with_pypdf(pdf_bytes: bytes) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        logger.info("pypdf not installed; OCR text fallback unavailable")
        return []

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception as exc:
        logger.warning("pypdf could not read PDF bytes: %s", str(exc)[:220])
        return []

    parsed_pages: list[dict[str, Any]] = []
    for page_index, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        if not lines:
            continue

        line_count = len(lines)
        line_objs: list[dict[str, Any]] = []
        for idx, line in enumerate(lines):
            step = 0.9 / max(1, line_count)
            y0 = min(0.95, 0.05 + (idx * step))
            y1 = min(0.99, y0 + max(0.01, step))
            line_objs.append(
                {
                    "text": line,
                    "confidence": 99.0,
                    "page": page_index,
                    "bbox": {"x0": 0.05, "y0": y0, "x1": 0.95, "y1": y1},
                }
            )
        parsed_pages.append(
            {
                "page": page_index,
                "lines": line_objs,
                "text": "\n".join(line["text"] for line in line_objs),
            }
        )
    return parsed_pages
