from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config import settings

try:
    import groq
except Exception:  # pragma: no cover - optional dependency in local env
    groq = None

VALID_CLAUSE_TYPES = [
    "Indemnity",
    "Liability",
    "Termination",
    "Payment",
    "Arbitration",
    "Confidentiality",
    "Non-compete",
    "Intellectual Property",
    "Governing Law",
    "Force Majeure",
    "Warranty",
    "Penalty",
    "Jurisdiction",
    "Definitions",
    "Representations",
    "Covenants",
    "Other",
]

def _load_statutes() -> list[dict[str, Any]]:
    try:
        path = settings.statutes_path
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # Keep backend booting even if statutes file is missing; fail-loud at answer level.
        return []


STATUTES: list[dict[str, Any]] = _load_statutes()
STATUTES_TEXT = json.dumps(STATUTES, indent=2, ensure_ascii=False)
logger = logging.getLogger("uvicorn.error")


def _get_groq_client():
    if groq is None or not settings.GROQ_API_KEY:
        return None
    return groq.AsyncGroq(api_key=settings.GROQ_API_KEY)


async def analyze_chunks_for_insights(
    chunks: list[dict[str, Any]],
    doc_id: str,
    case_id: str,
    user_id: str,
    db,
) -> int:
    insight_count = 0
    client = _get_groq_client()
    logger.info(
        "XRay analysis started: doc_id=%s chunks=%s anthropic_enabled=%s statutes=%s",
        doc_id,
        len(chunks),
        client is not None,
        len(STATUTES),
    )
    for chunk in chunks:
        content = str(chunk.get("content", "")).strip()
        if len(content) < 100:
            continue

        result = await _analyze_single_chunk(content, client)
        if not result:
            continue
        if result.get("anomaly_flag") == "NOT_A_CLAUSE":
            continue
        if not result.get("clause_type"):
            continue

        clause_type = str(result["clause_type"])
        if clause_type not in VALID_CLAUSE_TYPES:
            clause_type = "Other"

        anomaly_flag = str(result.get("anomaly_flag", "STANDARD"))
        if anomaly_flag not in {"HIGH_RISK", "MEDIUM_RISK", "STANDARD"}:
            anomaly_flag = "STANDARD"

        statutory_reference = result.get("statutory_reference")
        statutory_id = _resolve_statutory_id(statutory_reference)

        bbox = chunk.get("bbox", {})
        await db.execute(
            """
            INSERT INTO insights
                (id, document_id, case_id, user_id, clause_type, summary, anomaly_flag,
                 anomaly_reason, statutory_reference, statutory_id, page_number,
                 bbox_x0, bbox_y0, bbox_x1, bbox_y1, source_chunk_id)
            VALUES
                (uuid_generate_v4(), $1, $2, $3, $4, $5, $6,
                 $7, $8, $9, $10, $11, $12, $13, $14, $15)
            """,
            doc_id,
            case_id,
            user_id,
            clause_type,
            str(result.get("summary") or "").strip()[:1200] or "Clause analysis available.",
            anomaly_flag,
            result.get("anomaly_reason"),
            statutory_reference,
            statutory_id,
            int(chunk.get("page_number", 1)),
            float(bbox.get("x0", 0.0)),
            float(bbox.get("y0", 0.0)),
            float(bbox.get("x1", 1.0)),
            float(bbox.get("y1", 1.0)),
            chunk.get("id"),
        )
        insight_count += 1

    logger.info("XRay analysis completed: doc_id=%s insights=%s", doc_id, insight_count)
    return insight_count


async def _analyze_single_chunk(chunk_text: str, client) -> dict[str, Any] | None:
    if client is None:
        return _fallback_analyze_chunk(chunk_text)

    try:
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=600,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": _build_prompt(chunk_text)}],
        )
        raw = str(response.choices[0].message.content).strip()
        return json.loads(raw)
    except Exception:
        return _fallback_analyze_chunk(chunk_text)


def _build_prompt(chunk_text: str) -> str:
    return f"""You are a senior Indian corporate lawyer analyzing a clause from a legal document.

CLAUSE TEXT:
{chunk_text}

INDIAN STATUTES REFERENCE (only cite from this list):
{STATUTES_TEXT}

Analyze this clause and return ONLY valid JSON in exactly this format:
{{
  "clause_type": "<one of: {', '.join(VALID_CLAUSE_TYPES)} — or null if not a substantive legal clause>",
  "summary": "<one sentence plain-English explanation of what this clause does>",
  "anomaly_flag": "<HIGH_RISK | MEDIUM_RISK | STANDARD | NOT_A_CLAUSE>",
  "anomaly_reason": "<plain English explanation of the specific risk, or null if STANDARD or NOT_A_CLAUSE>",
  "statutory_reference": "<exact statute name and section from the reference list above that applies, or null>"
}}

Return ONLY the JSON object. No markdown fences."""


def _resolve_statutory_id(statutory_reference: Any) -> str | None:
    if not statutory_reference:
        return None
    reference = str(statutory_reference).lower()
    for statute in STATUTES:
        section = str(statute.get("section", "")).lower()
        title = str(statute.get("title", "")).lower()
        if section and section in reference:
            return statute.get("id")
        if title and title in reference:
            return statute.get("id")
    return None


def _fallback_analyze_chunk(chunk_text: str) -> dict[str, Any]:
    text = chunk_text.lower()
    heuristics = [
        ("indemn", "Indemnity", "HIGH_RISK"),
        ("arbitr", "Arbitration", "MEDIUM_RISK"),
        ("terminate", "Termination", "MEDIUM_RISK"),
        ("non-compete", "Non-compete", "HIGH_RISK"),
        ("governing law", "Governing Law", "STANDARD"),
        ("jurisdiction", "Jurisdiction", "STANDARD"),
        ("penalty", "Penalty", "HIGH_RISK"),
        ("liability", "Liability", "MEDIUM_RISK"),
    ]
    clause_type = None
    anomaly_flag = "STANDARD"
    for token, guessed_clause, guessed_flag in heuristics:
        if token in text:
            clause_type = guessed_clause
            anomaly_flag = guessed_flag
            break
    if clause_type is None:
        return {
            "clause_type": None,
            "summary": "",
            "anomaly_flag": "NOT_A_CLAUSE",
            "anomaly_reason": None,
            "statutory_reference": None,
        }

    matched_statute = _best_match_statute(text)
    summary = chunk_text.strip().replace("\n", " ")
    return {
        "clause_type": clause_type,
        "summary": summary[:240] if summary else "Clause extracted from document.",
        "anomaly_flag": anomaly_flag,
        "anomaly_reason": (
            "Potential drafting risk detected by heuristic fallback. "
            "Review manually because AI model is unavailable."
            if anomaly_flag != "STANDARD"
            else None
        ),
        "statutory_reference": matched_statute,
    }


def _best_match_statute(text: str) -> str | None:
    best_id: str | None = None
    best_score = 0
    for statute in STATUTES:
        score = 0
        for keyword in statute.get("keywords", []):
            keyword_lower = str(keyword).lower()
            if keyword_lower and keyword_lower in text:
                score += 1
        if score > best_score:
            best_score = score
            best_id = statute.get("id")
    if not best_id:
        return None
    statute = next((item for item in STATUTES if item.get("id") == best_id), None)
    if not statute:
        return None
    section = statute.get("section")
    act = statute.get("act")
    if section and act:
        return f"{section}, {act}"
    return section or act
