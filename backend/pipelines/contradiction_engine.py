from __future__ import annotations

import json
import logging
import time
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
        logger.error("[GROQ] Client not initialized or API key missing")
        return None
    return groq.AsyncGroq(api_key=settings.GROQ_API_KEY)


# =========================
# ENTRY POINT
# =========================
async def detect_contradictions_for_case(case_id: str, user_id: str) -> None:
    conn = await get_db_connection()
    start_time = time.time()

    try:
        logger.info(f"[SCAN START] case_id={case_id} user_id={user_id}")

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

        logger.info(f"[DOC FETCHED] count={len(documents)}")

        if len(documents) < 2:
            logger.warning("[SKIP] Not enough documents for comparison")
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

        seen_pairs = set()

        for doc_a, doc_b in combinations(documents, 2):

            pair_key = tuple(sorted([doc_a["id"], doc_b["id"]]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            logger.info(
                f"[PAIR] Comparing: {doc_a['original_filename']} vs {doc_b['original_filename']}"
            )

            try:
                await _compare_document_pair(
                    conn, case_id, user_id, dict(doc_a), dict(doc_b)
                )
            except Exception:
                logger.exception("[PAIR FAILED]")

    finally:
        duration = time.time() - start_time
        logger.info(f"[SCAN COMPLETE] case_id={case_id} time={duration:.2f}s")
        await release_db_connection(conn)


# =========================
# CORE PIPELINE
# =========================
async def _compare_document_pair(conn, case_id, user_id, doc_a, doc_b):

    logger.info(f"[FETCH CHUNKS] docA={doc_a['id']} docB={doc_b['id']}")

    chunks_a = await conn.fetch(
        """
        SELECT content, page_number, bbox_x0, bbox_y0, bbox_x1, bbox_y1
        FROM chunks WHERE document_id=$1 ORDER BY chunk_index ASC LIMIT 25
        """,
        doc_a["id"],
    )

    chunks_b = await conn.fetch(
        """
        SELECT content, page_number, bbox_x0, bbox_y0, bbox_x1, bbox_y1
        FROM chunks WHERE document_id=$1 ORDER BY chunk_index ASC LIMIT 25
        """,
        doc_b["id"],
    )

    logger.info(f"[CHUNKS] A={len(chunks_a)} B={len(chunks_b)}")

    if not chunks_a or not chunks_b:
        logger.warning("[SKIP] Missing chunks")
        return

    contradictions = await _llm_reasoning_layer(doc_a, doc_b, chunks_a, chunks_b)
    logger.info(f"[LLM OUTPUT] raw_count={len(contradictions)}")

    contradictions = _deduplicate(contradictions)
    logger.info(f"[DEDUP] count={len(contradictions)}")

    contradictions = await _validate_contradictions(contradictions)
    logger.info(f"[VALIDATED] count={len(contradictions)}")

    for c in contradictions:

        claim_a = c.get("claim_a", "").strip()
        claim_b = c.get("claim_b", "").strip()

        if not claim_a or not claim_b:
            continue

        bbox_a = _bbox_for_page(chunks_a, c.get("page_a"))
        bbox_b = _bbox_for_page(chunks_b, c.get("page_b"))

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
            c.get("page_a"),
            c.get("page_b"),
            bbox_a["x0"],
            bbox_a["y0"],
            bbox_a["x1"],
            bbox_a["y1"],
            bbox_b["x0"],
            bbox_b["y0"],
            bbox_b["x1"],
            bbox_b["y1"],
            c.get("severity", "MEDIUM"),
            c.get("explanation", "")[:1200],
        )


# =========================
# LLM REASONING
# =========================
async def _llm_reasoning_layer(doc_a, doc_b, chunks_a, chunks_b):

    client = _get_groq_client()
    if client is None:
        return []

    logger.info("[GROQ] Preparing prompt")

    def filter_chunks(chunks):
        important = []
        for c in chunks:
            t = c["content"].lower()
            if any(x in t for x in ["₹", "agreement", "date", "paid", "executed"]):
                important.append(c)
        return important[:12] if important else chunks[:8]

    chunks_a = filter_chunks(chunks_a)
    chunks_b = filter_chunks(chunks_b)

    text_a = "\n".join(f"[{c['page_number']}] {c['content']}" for c in chunks_a)[:2500]
    text_b = "\n".join(f"[{c['page_number']}] {c['content']}" for c in chunks_b)[:2500]

    prompt = f"""
You MUST return a valid JSON object.

IMPORTANT:
- Output MUST be strictly in JSON format
- Do NOT return anything outside JSON
- Ensure valid JSON syntax

Schema:
{{
 "contradictions":[
  {{
   "claim_a":"string",
   "page_a":1,
   "claim_b":"string",
   "page_b":1,
   "severity":"HIGH|MEDIUM",
   "confidence":0.0,
   "explanation":"string"
  }}
 ]
}}

Task:
Find ONLY contradictions where BOTH statements cannot be true.

Ignore:
- rewording
- extra details
- timeline elaboration

DOCUMENT A:
{text_a}

DOCUMENT B:
{text_b}
"""

    try:
        start = time.time()

        logger.info("[GROQ CALL] Sending request...")

        res = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            temperature=0,
            max_tokens=1000,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )

        duration = time.time() - start
        logger.info(f"[GROQ RESPONSE] time={duration:.2f}s")

        content = res.choices[0].message.content
        logger.debug(f"[GROQ RAW OUTPUT] {content[:500]}")

        parsed = json.loads(content)
        contradictions = parsed.get("contradictions", [])

        logger.info(f"[GROQ PARSED] count={len(contradictions)}")

        return contradictions

    except Exception as e:
        logger.exception(f"[GROQ FAILED] error={str(e)}")
        return []


# =========================
# VALIDATION
# =========================
async def _validate_contradictions(items: List[Dict]) -> List[Dict]:

    logger.info(f"[VALIDATION START] items={len(items)}")

    client = _get_groq_client()
    if client is None:
        return items

    validated = []

    for idx, item in enumerate(items):

        prompt = f"""
Can BOTH statements be true?

A: {item.get("claim_a")}
B: {item.get("claim_b")}

Answer ONLY YES or NO.
"""

        try:
            res = await client.chat.completions.create(
                model=settings.GROQ_MODEL,
                temperature=0,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )

            ans = res.choices[0].message.content.strip().upper()
            logger.debug(f"[VALIDATION RESULT {idx}] {ans}")

            if "NO" in ans:
                validated.append(item)

        except Exception:
            logger.exception("[VALIDATION ERROR]")

    logger.info(f"[VALIDATION COMPLETE] kept={len(validated)}")
    return validated


# =========================
# DEDUP
# =========================
def _deduplicate(items: List[Dict]) -> List[Dict]:
    seen = set()
    final = []

    for i in items:
        key = (i.get("claim_a", "")[:100], i.get("claim_b", "")[:100])
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