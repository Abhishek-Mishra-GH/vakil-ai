from __future__ import annotations

from typing import Any

from groq import AsyncGroq

from config import settings

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return _client


async def translate_pages(pages: list[dict[str, Any]], source_lang: str) -> list[dict[str, Any]]:
    """
    Best-effort translation to English.
    Keeps line geometry intact and only replaces line text.
    """
    if source_lang.lower().startswith("en"):
        return pages
    if not settings.GROQ_API_KEY:
        # Fail loud in status text at higher level if translation is required but unavailable.
        return pages

    client = _get_client()
    translated_pages: list[dict[str, Any]] = []
    for page in pages:
        translated_lines: list[dict[str, Any]] = []
        for line in page.get("lines", []):
            text = str(line.get("text", "")).strip()
            if not text:
                translated_lines.append(line)
                continue
            try:
                response = await client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[
                        {
                            "role": "user", 
                            "content": (
                                "Translate the following legal line to English. "
                                "Return only the translated text.\n\n"
                                f"{text}"
                            )
                        }
                    ],
                    temperature=0,
                )
                translated_text = str(response.choices[0].message.content).strip() or text
            except Exception:
                translated_text = text
            translated_lines.append({**line, "text": translated_text})

        translated_pages.append(
            {
                **page,
                "lines": translated_lines,
                "text": "\n".join(str(line["text"]) for line in translated_lines),
            }
        )
    return translated_pages
