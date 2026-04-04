from __future__ import annotations

import re
from typing import Any

from config import settings

SECTION_START_PATTERNS = [
    r"^\s*NOW[\s,]+THEREFORE",
    r"^\s*WHEREAS",
    r"^\s*IN WITNESS WHEREOF",
    r"^\s*SCHEDULE\s+[A-Z0-9]",
    r"^\s*ANNEXURE\s+[A-Z0-9]",
    r"^\s*EXHIBIT\s+[A-Z0-9]",
    r"^\s*Article\s+\d+[\.\s]",
    r"^\s*Section\s+\d+[\.\s]",
    r"^\s*SECTION\s+\d+[\.\s]",
    r"^\s*Clause\s+\d+[\.\s]",
    r"^\s*\d{1,2}\.\s+[A-Z][A-Z\s]{3,}",
    r"^\s*[A-Z][A-Z\s]{5,}:?\s*$",
]

SKIP_PATTERNS = [
    r"^\s*Page\s+\d+\s*(of\s+\d+)?\s*$",
    r"^\s*-\s*\d+\s*-\s*$",
    r"^\s*\d+\s*$",
    r"^\s*$",
]

SUBCLAUSE_SPLIT_PATTERN = re.compile(r"^\s*(\([a-z]\)|\([ivxlcdm]+\)|\d+\.\d+)\s+", re.IGNORECASE)


def is_section_start(text: str) -> bool:
    return any(re.match(pattern, text, re.IGNORECASE) for pattern in SECTION_START_PATTERNS)


def should_skip(text: str) -> bool:
    return any(re.match(pattern, text) for pattern in SKIP_PATTERNS)


def create_legal_chunks(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current_lines: list[dict[str, Any]] = []
    current_bbox: dict[str, float] | None = None
    current_header: str | None = None
    current_start_page: int = 1
    chunk_index = 0

    for page in pages:
        for line in page.get("lines", []):
            text = str(line.get("text", "")).strip()
            if should_skip(text):
                continue

            if is_section_start(text) and current_lines:
                chunk = _build_chunk(
                    current_lines,
                    current_start_page,
                    current_bbox,
                    current_header,
                    chunk_index,
                )
                if chunk:
                    chunk_index = _push_chunk_with_split(chunks, chunk, chunk_index)

                current_lines = []
                current_bbox = None
                current_header = text
                current_start_page = int(page.get("page", current_start_page))

            if not current_lines:
                current_start_page = int(page.get("page", current_start_page))

            current_lines.append(line)
            current_bbox = _expand_bbox(current_bbox, line.get("bbox", {}))

    if current_lines:
        chunk = _build_chunk(
            current_lines,
            current_start_page,
            current_bbox,
            current_header,
            chunk_index,
        )
        if chunk:
            _push_chunk_with_split(chunks, chunk, chunk_index)

    return [chunk for chunk in chunks if len(chunk["content"].strip()) >= settings.MIN_CHUNK_CHARS]


def _build_chunk(
    lines: list[dict[str, Any]],
    page_number: int,
    bbox: dict[str, float] | None,
    header: str | None,
    index: int,
) -> dict[str, Any] | None:
    content = "\n".join(str(line.get("text", "")).strip() for line in lines).strip()
    if len(content) < settings.MIN_CHUNK_CHARS:
        return None
    return {
        "content": content,
        "content_original": None,
        "page_number": page_number,
        "bbox": bbox or {"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0},
        "section_header": header,
        "chunk_index": index,
    }


def _expand_bbox(current: dict[str, float] | None, new_bbox: dict[str, Any]) -> dict[str, float]:
    x0 = float(new_bbox.get("x0", 0.0))
    y0 = float(new_bbox.get("y0", 0.0))
    x1 = float(new_bbox.get("x1", 1.0))
    y1 = float(new_bbox.get("y1", 1.0))
    if current is None:
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
    return {
        "x0": min(current["x0"], x0),
        "y0": min(current["y0"], y0),
        "x1": max(current["x1"], x1),
        "y1": max(current["y1"], y1),
    }


def _push_chunk_with_split(
    chunks: list[dict[str, Any]],
    chunk: dict[str, Any],
    chunk_index: int,
    max_chars: int = 7000,
) -> int:
    if len(chunk["content"]) <= max_chars:
        chunk["chunk_index"] = chunk_index
        chunks.append(chunk)
        return chunk_index + 1

    parts: list[str] = []
    buffer: list[str] = []
    current_chars = 0
    for line in chunk["content"].splitlines():
        line_len = len(line) + 1
        if buffer and current_chars + line_len > max_chars and SUBCLAUSE_SPLIT_PATTERN.match(line):
            parts.append("\n".join(buffer).strip())
            buffer = [line]
            current_chars = line_len
            continue
        buffer.append(line)
        current_chars += line_len
    if buffer:
        parts.append("\n".join(buffer).strip())

    for part in parts:
        if len(part) < settings.MIN_CHUNK_CHARS:
            continue
        new_chunk = {
            **chunk,
            "content": part,
            "chunk_index": chunk_index,
        }
        chunks.append(new_chunk)
        chunk_index += 1
    return chunk_index

