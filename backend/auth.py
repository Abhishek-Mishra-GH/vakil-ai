from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings
from database.connection import get_db

# Use PBKDF2 as primary scheme to avoid bcrypt backend/runtime issues
# (notably 72-byte password behavior changes in newer bcrypt builds).
# Keep bcrypt variants for legacy verification compatibility.
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        # Never crash auth flow for malformed/legacy hashes.
        return False


def create_access_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.JWT_EXPIRE_DAYS)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db=Depends(get_db),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await db.fetchrow(
        """
        SELECT id, email, full_name, is_active
        FROM users
        WHERE id=$1
        """,
        user_id,
    )
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "id": str(user["id"]),
        "email": user["email"],
        "full_name": user["full_name"],
        "is_active": user["is_active"],
    }
