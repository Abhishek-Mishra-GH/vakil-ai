from __future__ import annotations

from typing import Any

import httpx

from config import settings

IK_BASE_URL = "https://api.indiankanoon.org"
IK_SEARCH_URL = f"{IK_BASE_URL}/search/"


async def fetch_precedents(legal_issue: str, max_results: int = 2) -> list[dict[str, Any]]:
    if not settings.INDIAN_KANOON_API_KEY:
        return []

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                IK_SEARCH_URL,
                data={"formInput": legal_issue, "pagenum": 0},
                headers={"Authorization": f"Token {settings.INDIAN_KANOON_API_KEY}"},
            )
        if response.status_code != 200:
            return []
        data = response.json()
    except Exception:
        return []

    precedents: list[dict[str, Any]] = []
    for doc in data.get("docs", [])[:max_results]:
        publish_date = str(doc.get("publishdate", ""))
        precedents.append(
            {
                "title": doc.get("title", "Unknown Case"),
                "court": doc.get("docsource", "Unknown Court"),
                "year": publish_date[:4] if publish_date else "Unknown",
                "relevance_to": legal_issue,
                "citation": doc.get("citation", ""),
                "url": f"https://indiankanoon.org/doc/{doc.get('tid', '')}",
                "headline": str(doc.get("headline", ""))[:300],
            }
        )
    return precedents

