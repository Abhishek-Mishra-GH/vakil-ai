from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    # App
    APP_NAME: str = "VakilAI API"
    API_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql://legalai:legalai@localhost:5432/legalai"
    DB_POOL_MIN_SIZE: int = 2
    DB_POOL_MAX_SIZE: int = 10
    DB_COMMAND_TIMEOUT: int = 60
    AUTO_APPLY_SCHEMA: bool = True

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Paths
    STATUTES_PATH: str = str(DATA_DIR / "statutes.json")

    @field_validator("DEBUG", "AUTO_APPLY_SCHEMA", mode="before")
    @classmethod
    def _parse_debug(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @property
    def cors_origins(self) -> list[str]:
        cleaned = self.CORS_ORIGINS.strip()
        if not cleaned:
            return []
        if cleaned.startswith("["):
            import json

            parsed = json.loads(cleaned)
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in cleaned.split(",") if item.strip()]

    @property
    def statutes_path(self) -> Path:
        """
        Resolve STATUTES_PATH robustly across:
        - absolute paths
        - paths relative to repo root
        - paths relative to backend directory
        - current working directory
        """
        # raw = Path(self.STATUTES_PATH)
        # candidates: list[Path] = []
        # if raw.is_absolute():
        #     candidates.append(raw)
        # else:
        #     candidates.extend(
        #         [
        #             REPO_ROOT / raw,
        #             BACKEND_DIR / raw,
        #             Path.cwd() / raw,
        #             raw,
        #         ]
        #     )
        # for candidate in candidates:
        #     if candidate.exists():
        #         return candidate.resolve()
        # fallback to canonical project location
        return (DATA_DIR / "statutes.json").resolve()

    model_config = SettingsConfigDict(
        env_file=(str(BACKEND_DIR / ".env")),
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
