from __future__ import annotations

import json
from typing import Any

from config import settings
from services.indian_kanoon import fetch_precedents

try:
    import groq
except Exception:  # pragma: no cover
    groq = None


def _get_client():
    if groq is None or not settings.GROQ_API_KEY:
        return None
    return groq.AsyncGroq(api_key=settings.GROQ_API_KEY)


async def generate_brief(case_id: str, user_id: str, db) -> dict[str, Any]:
    case = await db.fetchrow("SELECT * FROM cases WHERE id=$1 AND user_id=$2", case_id, user_id)
    if not case:
        raise ValueError("Case not found")

    documents = await db.fetch(
        """
        SELECT id, original_filename
        FROM documents
        WHERE case_id=$1 AND user_id=$2 AND processing_status='ready'
        ORDER BY created_at ASC
        """,
        case_id,
        user_id,
    )
    if not documents:
        raise ValueError("No processed documents available for brief generation")

    all_chunks: list[dict[str, Any]] = []
    chunks_per_doc = max(10, 80 // len(documents))
    for document in documents:
        doc_chunks = await db.fetch(
            """
            SELECT content, page_number
            FROM chunks
            WHERE document_id=$1
            ORDER BY chunk_index ASC
            LIMIT $2
            """,
            document["id"],
            chunks_per_doc,
        )
        for chunk in doc_chunks:
            all_chunks.append(
                {
                    "filename": document["original_filename"],
                    "page": chunk["page_number"],
                    "content": chunk["content"],
                }
            )

    context = "\n\n---\n\n".join(
        f"SOURCE: {item['filename']}, Page {item['page']}\n{item['content']}"
        for item in all_chunks
    )[:8000]

    client = _get_client()
    if client is None:
        raise RuntimeError("LLM client not configured — GROQ_API_KEY is missing or groq library not installed.")
    
    brief_data = await _generate_brief_with_llm(client, case, documents, context)
    if brief_data is None:
        raise RuntimeError("LLM failed to generate a valid brief.")

    precedents: list[dict[str, Any]] = []
    for issue in brief_data.get("key_legal_issues", [])[:3]:
        issue_precedents = await fetch_precedents(str(issue), max_results=2)
        precedents.extend(issue_precedents)
    brief_data["precedents"] = precedents[:5]

    doc_ids = [str(document["id"]) for document in documents]
    await db.execute(
        """
        INSERT INTO hearing_briefs
            (id, case_id, user_id, core_contention, timeline, offensive_arguments,
             defensive_arguments, weak_points, key_legal_issues, precedents, documents_used)
        VALUES
            (uuid_generate_v4(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (case_id) DO UPDATE SET
            core_contention=EXCLUDED.core_contention,
            timeline=EXCLUDED.timeline,
            offensive_arguments=EXCLUDED.offensive_arguments,
            defensive_arguments=EXCLUDED.defensive_arguments,
            weak_points=EXCLUDED.weak_points,
            key_legal_issues=EXCLUDED.key_legal_issues,
            precedents=EXCLUDED.precedents,
            documents_used=EXCLUDED.documents_used,
            generated_at=NOW()
        """,
        case_id,
        user_id,
        brief_data["core_contention"],
        json.dumps(brief_data.get("timeline", [])),
        json.dumps(brief_data.get("offensive_arguments", [])),
        json.dumps(brief_data.get("defensive_arguments", [])),
        json.dumps(brief_data.get("weak_points", [])),
        json.dumps(brief_data.get("key_legal_issues", [])),
        json.dumps(brief_data.get("precedents", [])),
        json.dumps(doc_ids),
    )

    return brief_data


async def _generate_brief_with_llm(client, case, documents, context: str) -> dict[str, Any] | None:
    doc_list = ", ".join(document["original_filename"] for document in documents)
    prompt = f"""Case: {case['title']}
Court: {case.get('court_name', 'Not specified')} {case.get('court_number', '')}
Case Number: {case.get('case_number', 'Not specified')}
Hearing Date: {case.get('hearing_date', 'Not specified')}

Documents available: {doc_list}

CASE DOCUMENTS (with source citations):
{context}

Generate a complete pre-hearing brief as a JSON object with EXACTLY these keys and shapes:
{{
  "core_contention": "<one paragraph summarising the central dispute>",
  "timeline": [
    {{"date": "<ISO or human date>", "event": "<what happened>", "source": "<filename, Page N>"}}
  ],
  "offensive_arguments": [
    {{"argument": "<heading>", "strength": "<STRONG|MODERATE>", "basis": "<legal basis / reasoning>", "source": "<filename, Page N>"}}
  ],
  "defensive_arguments": [
    {{"anticipated_attack": "<opposing argument>", "counter": "<your rebuttal>", "source": "<filename, Page N>"}}
  ],
  "weak_points": [
    {{"issue": "<description>", "severity": "<HIGH|MEDIUM|LOW>", "source": "<filename, Page N>"}}
  ],
  "key_legal_issues": ["<issue string>", "<issue string>"]
}}
Provide exactly 3 offensive arguments and 2 defensive arguments.
Use only the supplied documents and cite sources as filename + page."""

    try:
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=3000,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system", 
                    "content": "You are a senior Indian litigation lawyer. Use ONLY provided documents, do not invent facts. Return valid JSON only."
                },
                {"role": "user", "content": prompt}
            ],
        )
        raw = str(response.choices[0].message.content).strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None
        return parsed
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Brief generation exception:", str(e))
        return None


