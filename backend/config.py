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

     # Auth
    JWT_SECRET_KEY: str = "replace-this-with-a-very-long-random-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Paths
    STATUTES_PATH: str = str(DATA_DIR / "statutes.json")

    
    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIM: int = 1536
    OPENAI_QA_MODEL: str = "gpt-4.1-mini"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # Groq
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Cohere
    COHERE_API_KEY: str = ""
    COHERE_RERANK_MODEL: str = "rerank-english-v3.0"

    # AWS Textract
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-south-1"

    # Cloudinary
    CLOUDINARY_URL: str = ""
    LOCAL_UPLOAD_DIR: str = str(DATA_DIR / "uploads")

    # Document pipeline
    OCR_CONFIDENCE_THRESHOLD: float = 60.0
    MIN_CHUNK_CHARS: int = 80
    MAX_UPLOAD_SIZE_MB: int = 50

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
