from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from groq import AsyncGroq
from pydantic import BaseModel, field_validator

from auth import get_current_user
from config import settings
from database.connection import get_db
from services.search import hybrid_search

router = APIRouter(prefix="/api/qa", tags=["qa"])

QA_CANNOT_DETERMINE = "Cannot determine based on uploaded documents."
QA_SYSTEM_PROMPT = """You are a legal document analysis assistant helping an Indian advocate understand their case files.

ABSOLUTE RULES:
1. Answer ONLY using the text provided in the context below. Never use outside knowledge about the facts of this case.
2. After every specific claim you make, add a citation in the format [Page X].
3. If the answer to the question cannot be found in the provided context, respond with EXACTLY this phrase and nothing else: "Cannot determine based on uploaded documents."
4. Never speculate. Never infer beyond what is explicitly written.
5. If multiple documents contain relevant information, synthesize them and cite each source.
6. Treat every unsupported assertion as a malpractice risk."""


class CreateSessionRequest(BaseModel):
    document_id: str
    case_id: str


class AskRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Question is required")
        return text


@router.post("/sessions", status_code=201)
async def create_session(payload: CreateSessionRequest, db=Depends(get_db), current_user=Depends(get_current_user)):
    document = await db.fetchrow(
        """
        SELECT id
        FROM documents
        WHERE id=$1 AND case_id=$2 AND user_id=$3
        """,
        payload.document_id,
        payload.case_id,
        current_user["id"],
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    session_id = str(uuid4())
    await db.execute(
        """
        INSERT INTO qa_sessions (id, document_id, case_id, user_id)
        VALUES ($1, $2, $3, $4)
        """,
        session_id,
        payload.document_id,
        payload.case_id,
        current_user["id"],
    )
    return {"session_id": session_id}


@router.post("/sessions/{session_id}/ask")
async def ask_question(
    session_id: str,
    payload: AskRequest,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = await db.fetchrow(
        """
        SELECT id, document_id, case_id
        FROM qa_sessions
        WHERE id=$1 AND user_id=$2
        """,
        session_id,
        current_user["id"],
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.execute(
        """
        INSERT INTO qa_messages (id, session_id, role, content)
        VALUES (uuid_generate_v4(), $1, 'user', $2)
        """,
        session_id,
        payload.question,
    )

    retrieved_chunks = await hybrid_search(
        query=payload.question,
        case_id=str(session["case_id"]),
        user_id=current_user["id"],
        db=db,
        document_id=str(session["document_id"]),
        top_k=5,
    )

    if not retrieved_chunks:
        answer = QA_CANNOT_DETERMINE
        cannot_determine = True
    else:
        answer = await _generate_answer(payload.question, retrieved_chunks)
        cannot_determine = answer.strip() == QA_CANNOT_DETERMINE

    retrieved_payload = [
        {
            "chunk_id": str(chunk["id"]),
            "page_number": chunk["page_number"],
            "bbox_x0": chunk.get("bbox_x0"),
            "bbox_y0": chunk.get("bbox_y0"),
            "bbox_x1": chunk.get("bbox_x1"),
            "bbox_y1": chunk.get("bbox_y1"),
            "rerank_score": chunk.get("rerank_score", chunk.get("vector_score", chunk.get("bm25_score"))),
        }
        for chunk in retrieved_chunks
    ]

    await db.execute(
        """
        INSERT INTO qa_messages (id, session_id, role, content, retrieved_chunks, cannot_determine)
        VALUES (uuid_generate_v4(), $1, 'assistant', $2, $3, $4)
        """,
        session_id,
        answer,
        json.dumps(retrieved_payload),
        cannot_determine,
    )

    return {
        "answer": answer,
        "cannot_determine": cannot_determine,
        "retrieved_chunks": retrieved_payload,
    }


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    session = await db.fetchrow("SELECT id FROM qa_sessions WHERE id=$1 AND user_id=$2", session_id, current_user["id"])
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    rows = await db.fetch(
        """
        SELECT role, content, retrieved_chunks, cannot_determine, created_at
        FROM qa_messages
        WHERE session_id=$1
        ORDER BY created_at ASC
        """,
        session_id,
    )
    return {"session_id": session_id, "messages": [dict(row) for row in rows]}


async def _generate_answer(question: str, chunks: list[dict]) -> str:
    context_text = "\n\n".join(
        f"[Page {chunk['page_number']}]\n{chunk['content']}" for chunk in chunks
    )[:9000]

    if not settings.GROQ_API_KEY:
        return _fallback_answer(chunks)

    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    try:
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"QUESTION:\n{question}\n\n"
                        f"CONTEXT:\n{context_text}\n\n"
                        "Answer now."
                    ),
                },
            ],
            temperature=0,
        )
        answer = str(response.choices[0].message.content).strip()
        if not answer:
            return _fallback_answer(chunks)
        return answer
    except Exception:
        return _fallback_answer(chunks)


def _fallback_answer(chunks: list[dict]) -> str:
    if not chunks:
        return QA_CANNOT_DETERMINE
    first = chunks[0]
    page = first.get("page_number", "?")
    text = str(first.get("content", "")).replace("\n", " ").strip()
    if not text:
        return QA_CANNOT_DETERMINE
    return f"{text[:260]} [Page {page}]"
