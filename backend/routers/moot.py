from __future__ import annotations

import base64
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, field_validator

from auth import get_current_user
from config import settings
from database.connection import get_db
from services.search import hybrid_search
from services.elevenlabs_speech import text_to_speech_with_settings, transcribe_audio_with_settings

try:
    import groq
except Exception:  # pragma: no cover
    groq = None

router = APIRouter(prefix="/api/moot", tags=["moot"])


def _get_client():
    if groq is None or not settings.GROQ_API_KEY:
        return None
    return groq.AsyncGroq(api_key=settings.GROQ_API_KEY)


def _coerce_json_object(value):
    """Normalize asyncpg JSON/JSONB values to Python objects.

    asyncpg may return JSONB columns as strings depending on configuration.
    For API responses we want consistent JSON objects (dict/list) or None.
    """

    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except Exception:
                return None
        return None
    return value


class CreateSessionRequest(BaseModel):
    case_id: str


class ArgueRequest(BaseModel):
    argument: str
    include_feedback: bool = False

    @field_validator("argument")
    @classmethod
    def validate_argument(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Argument is required")
        return text


class MootTtsRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Text is required")
        if len(text) > 4000:
            raise ValueError("Text is too long")
        return text


async def _generate_argument_feedback(
    *,
    argument: str,
    weak_points,
    key_issues,
    argument_chunks: list[dict],
) -> str:
    argument_text = (argument or "").strip()
    if not argument_text:
        return "State a clear claim, cite one document page, and anticipate the strongest rebuttal."

    def _normalize_jsonish_list(value):
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("[") or text.startswith("{"):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return parsed
                    return [parsed]
                except Exception:
                    return [value]
            return [value]
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    weak_points_list = _normalize_jsonish_list(weak_points)
    key_issues_list = _normalize_jsonish_list(key_issues)

    top_weak = ""
    if weak_points_list:
        first = weak_points_list[0]
        if isinstance(first, dict):
            top_weak = str(first.get("issue") or first.get("text") or "").strip()
        else:
            top_weak = str(first).strip()

    top_issue = ""
    if key_issues_list:
        first = key_issues_list[0]
        if isinstance(first, dict):
            top_issue = str(first.get("issue") or first.get("text") or "").strip()
        else:
            top_issue = str(first).strip()

    top_cite = ""
    if argument_chunks:
        try:
            top_cite = f"Page {argument_chunks[0].get('page_number', '?')}"
        except Exception:
            top_cite = ""

    client = _get_client()
    if client is None:
        pieces: list[str] = []
        if top_cite:
            pieces.append(f"Add a specific citation (e.g., {top_cite}) for your key factual assertion.")
        else:
            pieces.append("Add at least one page-number citation for your key factual assertion.")
        if top_weak:
            pieces.append(f"Pre-empt the likely attack point: {top_weak}.")
        if top_issue:
            pieces.append(f"Tie your submission back to the core issue: {top_issue}.")
        return " ".join(pieces)[:400]

    prompt = (
        "You are a strict moot coach for an Indian court hearing. "
        "Give 1-3 short sentences of actionable feedback to improve the USER'S argument. "
        "Focus on: (a) structure (issue → rule → application), (b) documentary/page citations, "
        "(c) anticipating the strongest rebuttal. Do NOT rewrite the argument."
    )

    context_lines: list[str] = []
    if top_issue:
        context_lines.append(f"Key issue: {top_issue}")
    if top_weak:
        context_lines.append(f"Known weak point: {top_weak}")
    if top_cite:
        context_lines.append(f"Closest record to cite: {top_cite}")

    user_msg = "\n".join([
        "Argument:",
        argument_text,
        "",
        "Context:",
        *(context_lines or ["(none)"]),
    ])

    try:
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=140,
            temperature=0.2,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
        )
        text = str(response.choices[0].message.content).strip()
        return text[:500]
    except Exception:
        # Non-fatal: feedback is optional.
        return "Add a page-number citation, address the key issue directly, and pre-empt the strongest rebuttal."


@router.post("/sessions", status_code=201)
async def create_session(payload: CreateSessionRequest, db=Depends(get_db), current_user=Depends(get_current_user)):
    case = await db.fetchrow(
        "SELECT id, title FROM cases WHERE id=$1 AND user_id=$2",
        payload.case_id,
        current_user["id"],
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    session_id = str(uuid4())
    await db.execute(
        """
        INSERT INTO moot_sessions (id, case_id, user_id, status)
        VALUES ($1, $2, $3, 'active')
        """,
        session_id,
        payload.case_id,
        current_user["id"],
    )
    return {"session_id": session_id, "status": "active", "case_title": case["title"]}


@router.get("/cases/{case_id}/sessions/history")
async def get_case_sessions_history(case_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    case = await db.fetchrow(
        "SELECT id, title FROM cases WHERE id=$1 AND user_id=$2",
        case_id,
        current_user["id"],
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    session_rows = await db.fetch(
        """
        SELECT id, case_id, status, exchange_count, summary, started_at, ended_at
        FROM moot_sessions
        WHERE case_id=$1 AND user_id=$2
        ORDER BY started_at DESC
        """,
        case_id,
        current_user["id"],
    )

    session_ids = [row["id"] for row in session_rows]
    messages_by_session: dict[str, list[dict]] = {str(session_id): [] for session_id in session_ids}

    if session_ids:
        message_rows = await db.fetch(
            """
            SELECT session_id, role, content, weak_point_hit, created_at
            FROM moot_messages
            WHERE session_id = ANY($1::uuid[])
            ORDER BY session_id, created_at ASC
            """,
            session_ids,
        )
        for row in message_rows:
            sid = str(row["session_id"])
            messages_by_session.setdefault(sid, []).append(
                {
                    "role": row["role"],
                    "content": row["content"],
                    "weak_point_hit": row["weak_point_hit"],
                    "created_at": row["created_at"],
                }
            )

    sessions: list[dict] = []
    for session in session_rows:
        sid = str(session["id"])
        sessions.append(
            {
                "session_id": sid,
                "case_id": str(session["case_id"]),
                "status": session["status"],
                "exchange_count": session["exchange_count"],
                "started_at": session["started_at"],
                "ended_at": session["ended_at"],
                "summary": _coerce_json_object(session["summary"]),
                "messages": messages_by_session.get(sid, []),
            }
        )

    return {"case_id": str(case["id"]), "case_title": case["title"], "sessions": sessions}


@router.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    session = await db.fetchrow(
        """
        SELECT
            s.id,
            s.case_id,
            s.status,
            s.exchange_count,
            s.summary,
            s.started_at,
            s.ended_at,
            c.title AS case_title
        FROM moot_sessions s
        JOIN cases c ON c.id = s.case_id
        WHERE s.id=$1 AND s.user_id=$2
        """,
        session_id,
        current_user["id"],
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = await db.fetch(
        """
        SELECT role, content, weak_point_hit, created_at
        FROM moot_messages
        WHERE session_id=$1
        ORDER BY created_at ASC
        """,
        session_id,
    )

    return {
        "session_id": str(session["id"]),
        "case_id": str(session["case_id"]),
        "case_title": session["case_title"],
        "status": session["status"],
        "exchange_count": session["exchange_count"],
        "started_at": session["started_at"],
        "ended_at": session["ended_at"],
        "summary": _coerce_json_object(session["summary"]),
        "messages": [dict(row) for row in rows],
    }


@router.post("/tts")
async def moot_tts(payload: MootTtsRequest, current_user=Depends(get_current_user)):
    # Authenticated endpoint to generate TTS for opponent messages on-demand.
    # No DB writes; safe to call repeatedly.
    _ = current_user  # ensure auth is enforced
    try:
        text = (payload.text or "").strip()
        if len(text) > 3500:
            text = text[:3500]
        tts_bytes, tts_mime = await text_to_speech_with_settings(text=text)
        if not tts_bytes:
            return {"tts_error": "No audio generated"}
        return {
            "tts_audio_base64": base64.b64encode(tts_bytes).decode("ascii"),
            "tts_mime": tts_mime,
        }
    except RuntimeError as exc:
        return {"tts_error": str(exc)}
    except Exception:
        return {"tts_error": "TTS generation failed"}


@router.post("/sessions/{session_id}/argue-audio")
async def argue_audio(
    session_id: str,
    file: UploadFile = File(...),
    include_tts: bool = Form(False),
    include_feedback: bool = Form(False),
    language_code: str | None = Form(None),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Mirror the text-based argument endpoint's session validation and exchange limit.
    session = await db.fetchrow(
        """
        SELECT
            s.id,
            s.case_id,
            s.status,
            s.exchange_count,
            c.title AS case_title,
            c.case_number,
            c.court_name
        FROM moot_sessions s
        JOIN cases c ON c.id = s.case_id
        WHERE s.id=$1 AND s.user_id=$2
        """,
        session_id,
        current_user["id"],
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] == "ended":
        raise HTTPException(status_code=400, detail="Session has ended")
    if session["exchange_count"] >= 20:
        raise HTTPException(status_code=400, detail="Session limit reached (20 exchanges)")

    file_bytes = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Audio is required")
    if len(file_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Audio exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit")

    audio_filename = (file.filename or "").strip() or "argument.webm"

    history_rows = await db.fetch(
        """
        SELECT role, content
        FROM moot_messages
        WHERE session_id=$1
        ORDER BY created_at ASC
        """,
        session_id,
    )
    conversation_history = [{"role": row["role"], "content": row["content"]} for row in history_rows]

    brief = await db.fetchrow(
        """
        SELECT weak_points, key_legal_issues
        FROM hearing_briefs
        WHERE case_id=$1 AND user_id=$2
        """,
        session["case_id"],
        current_user["id"],
    )
    weak_points = brief["weak_points"] if brief and brief["weak_points"] else []
    key_issues = brief["key_legal_issues"] if brief and brief["key_legal_issues"] else []

    relevant_chunks = await db.fetch(
        """
        SELECT ch.content, ch.page_number, d.original_filename
        FROM chunks ch
        JOIN documents d ON d.id = ch.document_id
        WHERE ch.case_id=$1 AND ch.user_id=$2
        ORDER BY ch.chunk_index ASC
        LIMIT 10
        """,
        session["case_id"],
        current_user["id"],
    )

    try:
        transcript_text = await transcribe_audio_with_settings(
            audio_bytes=file_bytes,
            filename=audio_filename,
            language_code=language_code,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(status_code=502, detail="Speech-to-text transcription failed")

    transcript_text = (transcript_text or "").strip()
    if not transcript_text:
        raise HTTPException(status_code=400, detail="Could not transcribe audio")

    argument_chunks = await hybrid_search(
        query=transcript_text,
        case_id=str(session["case_id"]),
        user_id=current_user["id"],
        db=db,
        top_k=3,
    )

    ai_response = await _generate_moot_reply(
        case_title=session["case_title"],
        case_number=session["case_number"],
        court_name=session["court_name"],
        exchange_count=session["exchange_count"],
        weak_points=weak_points,
        key_issues=key_issues,
        conversation_history=conversation_history,
        argument=transcript_text,
        relevant_chunks=[dict(chunk) for chunk in relevant_chunks],
        argument_chunks=argument_chunks,
    )
    weak_point_hit = "weak point" in ai_response.lower()

    argument_feedback: str | None = None
    if include_feedback:
        argument_feedback = await _generate_argument_feedback(
            argument=transcript_text,
            weak_points=weak_points,
            key_issues=key_issues,
            argument_chunks=argument_chunks,
        )

    await db.execute(
        """
        INSERT INTO moot_messages (id, session_id, role, content)
        VALUES (uuid_generate_v4(), $1, 'user', $2)
        """,
        session_id,
        transcript_text,
    )
    await db.execute(
        """
        INSERT INTO moot_messages (id, session_id, role, content, weak_point_hit)
        VALUES (uuid_generate_v4(), $1, 'assistant', $2, $3)
        """,
        session_id,
        ai_response,
        weak_point_hit,
    )

    exchange_count = int(session["exchange_count"]) + 1
    await db.execute("UPDATE moot_sessions SET exchange_count=$1 WHERE id=$2", exchange_count, session_id)

    result: dict[str, object] = {
        "response": ai_response,
        "transcript_text": transcript_text,
        "exchange_count": exchange_count,
        "session_active": exchange_count < 20,
        "weak_point_hit": weak_point_hit,
    }

    if argument_feedback:
        result["argument_feedback"] = argument_feedback

    if include_tts:
        try:
            tts_input = (ai_response or "").strip()
            # Keep within ElevenLabs payload limits and avoid upstream 400s.
            if len(tts_input) > 3500:
                tts_input = tts_input[:3500]
            tts_bytes, tts_mime = await text_to_speech_with_settings(text=tts_input)
            if tts_bytes:
                result["tts_audio_base64"] = base64.b64encode(tts_bytes).decode("ascii")
                result["tts_mime"] = tts_mime
        except RuntimeError as exc:
            # Missing ElevenLabs config / upstream 4xx should not break the core STT->moot flow.
            result["tts_error"] = str(exc)
        except Exception:
            result["tts_error"] = "TTS generation failed"

    return result


@router.post("/sessions/{session_id}/argue")
async def argue(
    session_id: str,
    payload: ArgueRequest,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = await db.fetchrow(
        """
        SELECT
            s.id,
            s.case_id,
            s.status,
            s.exchange_count,
            c.title AS case_title,
            c.case_number,
            c.court_name
        FROM moot_sessions s
        JOIN cases c ON c.id = s.case_id
        WHERE s.id=$1 AND s.user_id=$2
        """,
        session_id,
        current_user["id"],
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] == "ended":
        raise HTTPException(status_code=400, detail="Session has ended")
    if session["exchange_count"] >= 20:
        raise HTTPException(status_code=400, detail="Session limit reached (20 exchanges)")

    history_rows = await db.fetch(
        """
        SELECT role, content
        FROM moot_messages
        WHERE session_id=$1
        ORDER BY created_at ASC
        """,
        session_id,
    )
    conversation_history = [{"role": row["role"], "content": row["content"]} for row in history_rows]

    brief = await db.fetchrow(
        """
        SELECT weak_points, key_legal_issues
        FROM hearing_briefs
        WHERE case_id=$1 AND user_id=$2
        """,
        session["case_id"],
        current_user["id"],
    )
    weak_points = brief["weak_points"] if brief and brief["weak_points"] else []
    key_issues = brief["key_legal_issues"] if brief and brief["key_legal_issues"] else []

    relevant_chunks = await db.fetch(
        """
        SELECT ch.content, ch.page_number, d.original_filename
        FROM chunks ch
        JOIN documents d ON d.id = ch.document_id
        WHERE ch.case_id=$1 AND ch.user_id=$2
        ORDER BY ch.chunk_index ASC
        LIMIT 10
        """,
        session["case_id"],
        current_user["id"],
    )
    argument_chunks = await hybrid_search(
        query=payload.argument,
        case_id=str(session["case_id"]),
        user_id=current_user["id"],
        db=db,
        top_k=3,
    )

    ai_response = await _generate_moot_reply(
        case_title=session["case_title"],
        case_number=session["case_number"],
        court_name=session["court_name"],
        exchange_count=session["exchange_count"],
        weak_points=weak_points,
        key_issues=key_issues,
        conversation_history=conversation_history,
        argument=payload.argument,
        relevant_chunks=[dict(chunk) for chunk in relevant_chunks],
        argument_chunks=argument_chunks,
    )

    weak_point_hit = "weak point" in ai_response.lower()

    argument_feedback: str | None = None
    if payload.include_feedback:
        argument_feedback = await _generate_argument_feedback(
            argument=payload.argument,
            weak_points=weak_points,
            key_issues=key_issues,
            argument_chunks=argument_chunks,
        )

    await db.execute(
        """
        INSERT INTO moot_messages (id, session_id, role, content)
        VALUES (uuid_generate_v4(), $1, 'user', $2)
        """,
        session_id,
        payload.argument,
    )
    await db.execute(
        """
        INSERT INTO moot_messages (id, session_id, role, content, weak_point_hit)
        VALUES (uuid_generate_v4(), $1, 'assistant', $2, $3)
        """,
        session_id,
        ai_response,
        weak_point_hit,
    )

    exchange_count = int(session["exchange_count"]) + 1
    await db.execute(
        "UPDATE moot_sessions SET exchange_count=$1 WHERE id=$2",
        exchange_count,
        session_id,
    )

    result: dict[str, object] = {
        "response": ai_response,
        "exchange_count": exchange_count,
        "session_active": exchange_count < 20,
        "weak_point_hit": weak_point_hit,
    }

    if argument_feedback:
        result["argument_feedback"] = argument_feedback

    return result


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    session = await db.fetchrow(
        "SELECT id FROM moot_sessions WHERE id=$1 AND user_id=$2",
        session_id,
        current_user["id"],
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = await db.fetch(
        """
        SELECT role, content, weak_point_hit
        FROM moot_messages
        WHERE session_id=$1
        ORDER BY created_at ASC
        """,
        session_id,
    )
    summary = await _generate_summary([dict(row) for row in rows])
    await db.execute(
        """
        UPDATE moot_sessions
        SET status='ended', ended_at=NOW(), summary=$1
        WHERE id=$2
        """,
        json.dumps(summary),
        session_id,
    )
    return {"summary": summary}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    session = await db.fetchrow(
        """
        SELECT id, exchange_count, status
        FROM moot_sessions
        WHERE id=$1 AND user_id=$2
        """,
        session_id,
        current_user["id"],
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    rows = await db.fetch(
        """
        SELECT role, content, weak_point_hit, created_at
        FROM moot_messages
        WHERE session_id=$1
        ORDER BY created_at ASC
        """,
        session_id,
    )
    return {
        "session_id": session_id,
        "exchange_count": session["exchange_count"],
        "status": session["status"],
        "messages": [dict(row) for row in rows],
    }


async def _generate_moot_reply(
    case_title: str,
    case_number: str,
    court_name: str,
    exchange_count: int,
    weak_points,
    key_issues,
    conversation_history: list[dict],
    argument: str,
    relevant_chunks: list[dict],
    argument_chunks: list[dict],
) -> str:
    client = _get_client()
    if client is None:
        return _fallback_moot_reply(argument, weak_points, argument_chunks)

    def _normalize_jsonish_list(value):
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("[") or text.startswith("{"):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return parsed
                    return [parsed]
                except Exception:
                    return [value]
            return [value]
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    weak_points_list = _normalize_jsonish_list(weak_points)
    key_issues_list = _normalize_jsonish_list(key_issues)

    def _format_weak_point(item) -> str:
        if isinstance(item, dict):
            severity = item.get("severity") or "MEDIUM"
            issue = item.get("issue") or item.get("text") or ""
            return f"- [{severity}] {issue or json.dumps(item, ensure_ascii=False)}"
        return f"- [MEDIUM] {str(item)}"

    def _format_key_issue(item) -> str:
        if isinstance(item, dict):
            return f"- {item.get('issue') or item.get('text') or json.dumps(item, ensure_ascii=False)}"
        return f"- {str(item)}"

    weak_points_text = "\n".join(_format_weak_point(item) for item in weak_points_list) or "No specific weak points identified."
    key_issues_text = "\n".join(_format_key_issue(issue) for issue in key_issues_list) or "Not specified."
    doc_context = "\n\n".join(
        f"[{chunk['original_filename']}, Page {chunk['page_number']}]\n{chunk['content']}"
        for chunk in relevant_chunks
    )[:3000]
    argument_context = "\n\n".join(
        f"[Page {chunk['page_number']}]\n{chunk['content']}" for chunk in argument_chunks
    )[:1500]

    difficulty = "moderate"
    if exchange_count >= 3:
        difficulty = "aggressive"
    if exchange_count >= 8:
        difficulty = "senior counsel level"

    system_prompt = f"""You are senior opposing counsel in an Indian court moot session.

CASE: {case_title} ({case_number}) — {court_name}
WEAK POINTS:
{weak_points_text}
KEY ISSUES:
{key_issues_text}
CASE CONTEXT:
{doc_context}
RELEVANT TO CURRENT ARGUMENT:
{argument_context}

Rules:
1. Keep responses 2-4 sentences.
2. Challenge evidentiary gaps and weak points.
3. End with a pointed question/challenge.
4. If a major weakness is hit, append: "⚠ Weak point exploited".
5. Difficulty level: {difficulty}"""

    messages = conversation_history + [{"role": "user", "content": argument}]
    try:
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=400,
            temperature=0.3,
            messages=[{"role": "system", "content": system_prompt}] + messages,
        )
        text = str(response.choices[0].message.content).strip()
        return text or _fallback_moot_reply(argument, weak_points, argument_chunks)
    except Exception:
        return _fallback_moot_reply(argument, weak_points, argument_chunks)


def _fallback_moot_reply(argument: str, weak_points, argument_chunks: list[dict]) -> str:
    weak_issue = None
    if weak_points:
        first = weak_points[0]
        if isinstance(first, dict):
            weak_issue = first.get("issue")
        else:
            weak_issue = str(first)
    chunk_hint = ""
    if argument_chunks:
        chunk_hint = f" Your own records at Page {argument_chunks[0]['page_number']} require closer scrutiny."
    weak_fragment = f" The brief highlights: {weak_issue}." if weak_issue else ""
    return (
        "My learned friend, the submission lacks documentary precision and does not neutralize material vulnerabilities."
        f"{weak_fragment}{chunk_hint} How do you reconcile this gap before the court? ⚠ Weak point exploited"
    )


async def _generate_summary(messages: list[dict]) -> dict:
    weak_hits = sum(1 for message in messages if message.get("weak_point_hit"))
    if not messages:
        return {
            "strong_arguments": [],
            "weak_arguments": [],
            "weak_points_hit": 0,
            "coaching_tip": "Run at least one argument round before ending the session.",
            "overall_assessment": "DEVELOPING",
        }

    client = _get_client()
    if client is None:
        return {
            "strong_arguments": ["You consistently presented your position with courtroom structure."],
            "weak_arguments": ["Several responses lacked page-specific documentary citations."],
            "weak_points_hit": weak_hits,
            "coaching_tip": "Prepare page-numbered rebuttal notes for each likely attack point.",
            "overall_assessment": "NEEDS_WORK" if weak_hits > 0 else "DEVELOPING",
        }

    conversation = "\n\n".join(
        f"{'ADVOCATE' if message['role'] == 'user' else 'OPPOSING COUNSEL'}: {message['content']}"
        for message in messages
    )
    prompt = f"""Review this moot court session and return ONLY JSON:
{{
  "strong_arguments": ["..."],
  "weak_arguments": ["..."],
  "weak_points_hit": {weak_hits},
  "coaching_tip": "...",
  "overall_assessment": "<STRONG | NEEDS_WORK | DEVELOPING>"
}}

SESSION:
{conversation}"""
    try:
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=600,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = json.loads(str(response.choices[0].message.content).strip())
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {
        "strong_arguments": ["Argument quality could not be auto-scored due to summary generation failure."],
        "weak_arguments": ["Session summary generation encountered an internal error."],
        "weak_points_hit": weak_hits,
        "coaching_tip": "Re-run summary after confirming LLM configuration.",
        "overall_assessment": "DEVELOPING",
    }
