from __future__ import annotations

import mimetypes
from typing import Any

import httpx

from config import settings

ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_TTS_URL_BASE = "https://api.elevenlabs.io/v1/text-to-speech"


def _safe_error_detail(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
        if isinstance(payload, dict):
            raw = payload.get("detail") or payload.get("message") or payload.get("error")
            if isinstance(raw, str):
                return raw.strip()[:300]
            if raw is not None:
                return str(raw).strip()[:300]
            return str(payload).strip()[:300]
        return str(payload).strip()[:300]
    except Exception:
        try:
            return (resp.text or "").strip()[:300]
        except Exception:
            return ""


async def _post_with_retries(*, url: str, client: httpx.AsyncClient, max_retries: int = 2, **kwargs) -> httpx.Response:
    """POST with small retry for transient upstream failures (429/5xx)."""
    import asyncio

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = await client.post(url, **kwargs)
            if resp.status_code in {429, 500, 502, 503, 504} and attempt < max_retries:
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            return resp
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt < max_retries:
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("Request failed")


def _output_format_to_mime(output_format: str) -> str:
    # ElevenLabs output_format examples:
    # - mp3_44100_128
    # - wav_44100
    # - pcm_16000
    lower = (output_format or "").lower()
    if lower.startswith("mp3_"):
        return "audio/mpeg"
    if lower.startswith("wav_"):
        return "audio/wav"
    if lower.startswith("opus_"):
        return "audio/opus"

    guessed, _ = mimetypes.guess_type(f"file.{output_format}")
    return guessed or "application/octet-stream"


async def transcribe_audio(
    *,
    api_key: str,
    audio_bytes: bytes,
    filename: str,
    stt_model_id: str,
    language_code: str | None = None,
) -> str:
    if not api_key:
        raise RuntimeError("ElevenLabs API key is missing")

    headers = {"xi-api-key": api_key}
    data: dict[str, Any] = {
        "model_id": stt_model_id,
        # When passing encoded audio (e.g. webm/opus from browser), 'other' is correct.
        "file_format": "other",
        # Turn this on to reduce hallucinated or missing sounds.
        "tag_audio_events": "true",
        "timestamps_granularity": "word",
    }
    if language_code:
        data["language_code"] = language_code

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await _post_with_retries(
            url=ELEVENLABS_STT_URL,
            client=client,
            headers=headers,
            data=data,
            files={"file": (filename, audio_bytes, "application/octet-stream")},
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = getattr(exc.response, "status_code", "?")
            detail = _safe_error_detail(exc.response)
            message = f"ElevenLabs STT failed ({status})"
            if detail:
                message += f": {detail}"
            raise RuntimeError(message) from exc
        payload = resp.json()

    # Typical response includes `text` at top-level when not multichannel.
    if isinstance(payload, dict):
        text = payload.get("text") or payload.get("transcript") or ""
        if isinstance(text, str):
            return text.strip()

        # If we ever get multichannel/other structures.
        transcripts = payload.get("transcripts")
        if isinstance(transcripts, list):
            parts: list[str] = []
            for t in transcripts:
                if isinstance(t, dict) and isinstance(t.get("text"), str):
                    parts.append(t["text"])
            return "\n".join(parts).strip()

    return ""


async def text_to_speech(
    *,
    api_key: str,
    text: str,
    voice_id: str,
    tts_model_id: str,
    output_format: str,
    voice_settings: dict[str, Any] | None = None,
    apply_text_normalization: str | None = None,
) -> tuple[bytes, str]:
    if not api_key:
        raise RuntimeError("ElevenLabs API key is missing")
    if not voice_id:
        raise RuntimeError("ElevenLabs voice id is missing")
    if not text.strip():
        return b"", _output_format_to_mime(output_format)

    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    params = {"output_format": output_format}
    body: dict[str, Any] = {"text": text, "model_id": tts_model_id}
    if voice_settings:
        body["voice_settings"] = voice_settings
    if apply_text_normalization:
        body["apply_text_normalization"] = apply_text_normalization

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await _post_with_retries(
            url=ELEVENLABS_TTS_URL_BASE + f"/{voice_id}",
            client=client,
            headers=headers,
            params=params,
            json=body,
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Surface a concise, actionable error message (no secrets).
            status = getattr(exc.response, "status_code", "?")
            detail = _safe_error_detail(exc.response)
            message = f"ElevenLabs TTS failed ({status})"
            if detail:
                message += f": {detail}"
            raise RuntimeError(message) from exc

        return resp.content, _output_format_to_mime(output_format)


async def transcribe_audio_with_settings(
    *,
    audio_bytes: bytes,
    filename: str,
    language_code: str | None = None,
) -> str:
    return await transcribe_audio(
        api_key=settings.ELEVENLABS_API_KEY,
        audio_bytes=audio_bytes,
        filename=filename,
        stt_model_id=settings.ELEVENLABS_STT_MODEL_ID,
        language_code=language_code,
    )


async def text_to_speech_with_settings(
    *,
    text: str,
    voice_id: str | None = None,
    include_output_format: bool = True,
) -> tuple[bytes, str]:
    resolved_voice_id = voice_id or settings.ELEVENLABS_VOICE_ID
    voice_settings = {
        "stability": settings.ELEVENLABS_TTS_STABILITY,
        "similarity_boost": settings.ELEVENLABS_TTS_SIMILARITY_BOOST,
        "style": settings.ELEVENLABS_TTS_STYLE,
        "speed": settings.ELEVENLABS_TTS_SPEED,
        "use_speaker_boost": settings.ELEVENLABS_TTS_USE_SPEAKER_BOOST,
    }
    normalization = (settings.ELEVENLABS_TTS_APPLY_TEXT_NORMALIZATION or "").strip().lower()
    apply_norm = normalization if normalization in {"auto", "on", "off"} else "auto"
    return await text_to_speech(
        api_key=settings.ELEVENLABS_API_KEY,
        text=text,
        voice_id=resolved_voice_id,
        tts_model_id=settings.ELEVENLABS_TTS_MODEL_ID,
        output_format=settings.ELEVENLABS_TTS_OUTPUT_FORMAT if include_output_format else settings.ELEVENLABS_TTS_OUTPUT_FORMAT,
        voice_settings=voice_settings,
        apply_text_normalization=apply_norm,
    )

