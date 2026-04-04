from __future__ import annotations

from uuid import uuid4

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator

from auth import create_access_token, get_current_user, hash_password, verify_password
from database.connection import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    bar_council_id: str | None = None
    phone: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(value.encode("utf-8")) > 256:
            raise ValueError("Password must be at most 256 bytes")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Password is required")
        if len(value.encode("utf-8")) > 256:
            raise ValueError("Password must be at most 256 bytes")
        return value


@router.post("/register")
async def register(payload: RegisterRequest, db=Depends(get_db)):
    try:
        existing = await db.fetchrow("SELECT id FROM users WHERE email=$1", payload.email.lower())
    except asyncpg.UndefinedTableError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database schema not initialized. Apply backend/database/schema.sql and retry.",
        ) from exc
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid4())
    try:
        hashed_password = hash_password(payload.password)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Password format not supported. Use up to 256 characters.",
        ) from exc

    await db.execute(
        """
        INSERT INTO users (id, email, hashed_password, full_name, bar_council_id, phone)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        user_id,
        payload.email.lower(),
        hashed_password,
        payload.full_name.strip(),
        payload.bar_council_id,
        payload.phone,
    )
    token = create_access_token(user_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user_id, "email": payload.email.lower(), "full_name": payload.full_name.strip()},
    }


@router.post("/login")
async def login(payload: LoginRequest, db=Depends(get_db)):
    try:
        user = await db.fetchrow(
            """
            SELECT id, email, full_name, hashed_password, is_active
            FROM users
            WHERE email=$1
            """,
            payload.email.lower(),
        )
    except asyncpg.UndefinedTableError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database schema not initialized. Apply backend/database/schema.sql and retry.",
        ) from exc
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account deactivated")

    token = create_access_token(str(user["id"]))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user["id"]),
            "email": user["email"],
            "full_name": user["full_name"],
        },
    }


@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    return current_user
