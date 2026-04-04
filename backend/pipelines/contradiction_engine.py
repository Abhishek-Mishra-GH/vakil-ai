from __future__ import annotations

import json
import logging
import time
import asyncio
from itertools import combinations
from typing import Any, List, Dict

from config import settings
from database import get_db_connection, release_db_connection

try:
    import groq
except Exception:
    groq = None

logger = logging.getLogger("uvicorn.error")


# =========================
# CLIENT
# =========================
def _get_groq_client():
    if groq is None or not settings.GROQ_API_KEY:
        logger.error("[GROQ] Client not initialized")
        return None
    return groq.AsyncGroq(api_key=settings.GROQ_API_KEY)


# =========================
# SAFE PARSERS
# =========================
def _safe_int(val):
    try:
        if isinstance(val, int):
            return val

        if isinstance(val, str):
            val = val.strip().upper().replace("A:", "").replace("B:", "")
            return int(val)
    except Exception:
        return None
    return None


# =========================
# ENTRY POINT
# =========================
async def detect_contradictions_for_case(case_id: str, user_id: str) -> None:
    conn = await get_db_connection()
    start_time = time.time()

    try:
        logger.info(f"[SCAN START] case_id={case_id}")

        documents = await conn.fetch(
            """
            SELECT id, original_filename
            FROM documents
            WHERE case_id=$1 AND user_id=$2 AND processing_status='ready'
            ORDER BY created_at ASC
            """,
            case_id,
            user_id,
        )

        if len(documents) < 2:
            await conn.execute(
                "DELETE FROM contradictions WHERE case_id=$1 AND user_id=$2",
                case_id,
                user_id,
            )
            return

        await conn.execute(
            "DELETE FROM contradictions WHERE case_id=$1 AND user_id=$2",
            case_id,
            user_id,
        )

        for doc_a, doc_b in combinations(documents, 2):
            try:
                await _compare_document_pair(
                    conn, case_id, user_id, dict(doc_a), dict(doc_b)
                )
            except Exception:
                logger.exception("[PAIR FAILED]")

    finally:
        duration = time.time() - start_time
        logger.info(f"[SCAN COMPLETE] {duration:.2f}s")
        await release_db_connection(conn)


# =========================
# CORE PIPELINE
# =========================
async def _compare_document_pair(conn, case_id, user_id, doc_a, doc_b):

    chunks_a = await conn.fetch(
        """
        SELECT content, page_number, bbox_x0, bbox_y0, bbox_x1, bbox_y1
        FROM chunks WHERE document_id=$1 ORDER BY chunk_index ASC LIMIT 80
        """,
        doc_a["id"],
    )

    chunks_b = await conn.fetch(
        """
        SELECT content, page_number, bbox_x0, bbox_y0, bbox_x1, bbox_y1
        FROM chunks WHERE document_id=$1 ORDER BY chunk_index ASC LIMIT 80
        """,
        doc_b["id"],
    )

    if not chunks_a or not chunks_b:
        return

    # 🔥 PARALLEL LLM CALLS
    tasks = []
    for i in range(0, len(chunks_a), 20):
        for j in range(0, len(chunks_b), 20):
            tasks.append(
                _llm_reasoning_layer(
                    doc_a,
                    doc_b,
                    chunks_a[i:i+20],
                    chunks_b[j:j+20]
                )
            )

    results = await asyncio.gather(*tasks)

    contradictions = []
    for r in results:
        contradictions.extend(r)

    contradictions = _deduplicate(contradictions)
    contradictions = _filter_contradictions(contradictions)

    for c in contradictions:

        claim_a = c.get("claim_a", "").strip()
        claim_b = c.get("claim_b", "").strip()

        page_a = _safe_int(c.get("page_a"))
        page_b = _safe_int(c.get("page_b"))

        if not claim_a or not claim_b or page_a is None or page_b is None:
            continue

        bbox_a = _bbox_for_page(chunks_a, page_a)
        bbox_b = _bbox_for_page(chunks_b, page_b)

        await conn.execute(
            """
            INSERT INTO contradictions
            (id, case_id, user_id, doc_a_id, doc_b_id,
             claim_a, claim_b, page_a, page_b,
             bbox_x0_a, bbox_y0_a, bbox_x1_a, bbox_y1_a,
             bbox_x0_b, bbox_y0_b, bbox_x1_b, bbox_y1_b,
             severity, explanation)
            VALUES
            (uuid_generate_v4(), $1,$2,$3,$4,$5,$6,$7,$8,
             $9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
            """,
            case_id,
            user_id,
            doc_a["id"],
            doc_b["id"],
            claim_a[:3000],
            claim_b[:3000],
            page_a,
            page_b,
            bbox_a["x0"],
            bbox_a["y0"],
            bbox_a["x1"],
            bbox_a["y1"],
            bbox_b["x0"],
            bbox_b["y0"],
            bbox_b["x1"],
            bbox_b["y1"],
            c.get("severity", "MEDIUM"),
            c.get("explanation", "")[:1500],
        )


# =========================
# LLM REASONING
# =========================
async def _llm_reasoning_layer(doc_a, doc_b, chunks_a, chunks_b):

    client = _get_groq_client()
    if client is None:
        return []

    text_a = "\n".join(
        f"[A:{c['page_number']}] {c['content']}" for c in chunks_a
    )[:6000]

    text_b = "\n".join(
        f"[B:{c['page_number']}] {c['content']}" for c in chunks_b
    )[:6000]

    prompt = f"""
You are a HIGH-RECALL LEGAL CONTRADICTION ENGINE.

Find ALL contradictions.

Include:
- factual conflicts
- numeric mismatches
- date/time conflicts
- logical inconsistencies

IMPORTANT:
- page_a and page_b must be INTEGER only (e.g., 2, not "A:2")

Return STRICT JSON:

{{
 "contradictions":[
  {{
   "claim_a":"",
   "page_a":1,
   "claim_b":"",
   "page_b":1,
   "type":"FACTUAL|NUMERIC|TEMPORAL|LOGICAL",
   "severity":"HIGH|MEDIUM|LOW",
   "confidence":0.0,
   "explanation":"Explain clearly WHY both cannot be true."
  }}
 ]
}}

DOCUMENT A:
{text_a}

DOCUMENT B:
{text_b}
"""

    try:
        res = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )

        parsed = json.loads(res.choices[0].message.content)
        return parsed.get("contradictions", [])

    except Exception:
        logger.exception("[LLM ERROR]")
        return []


# =========================
# FILTER
# =========================
def _filter_contradictions(items: List[Dict]) -> List[Dict]:
    final = []
    for i in items:
        confidence = float(i.get("confidence", 0))
        severity = i.get("severity", "LOW")

        if confidence >= 0.5 or severity == "HIGH":
            final.append(i)

    return final


# =========================
# DEDUP
# =========================
def _deduplicate(items: List[Dict]) -> List[Dict]:
    seen = set()
    final = []

    for i in items:
        key = (
            i.get("claim_a", "")[:150],
            i.get("claim_b", "")[:150],
            i.get("type", "")
        )

        if key in seen:
            continue

        seen.add(key)
        final.append(i)

    return final


# =========================
# BBOX
# =========================
def _bbox_for_page(chunks, page_number: Any) -> Dict[str, float]:
    try:
        page_number = int(page_number)
    except Exception:
        return {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9}

    for row in chunks:
        if int(row["page_number"]) == page_number:
            return {
                "x0": float(row.get("bbox_x0") or 0.1),
                "y0": float(row.get("bbox_y0") or 0.1),
                "x1": float(row.get("bbox_x1") or 0.9),
                "y1": float(row.get("bbox_y1") or 0.9),
            }

    return {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9}