from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg

from config import BACKEND_DIR, settings

_pool: asyncpg.Pool | None = None
SCHEMA_PATH = BACKEND_DIR / "database" / "schema.sql"


async def create_pool() -> None:
    global _pool
    if _pool is not None:
        return
    _pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=settings.DB_POOL_MIN_SIZE,
        max_size=settings.DB_POOL_MAX_SIZE,
        command_timeout=settings.DB_COMMAND_TIMEOUT,
    )

    if _pool is None:
        raise RuntimeError("Failed to create database connection pool.")
    await _ensure_schema_initialized(_pool)


async def close_pool() -> None:
    global _pool
    if _pool is None:
        return
    await _pool.close()
    _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call create_pool() at startup.")
    return _pool


@asynccontextmanager
async def _acquire_connection() -> AsyncIterator[asyncpg.Connection]:
    if _pool is None:
        await create_pool()
    assert _pool is not None
    conn = await _pool.acquire()
    try:
        yield conn
    finally:
        await _pool.release(conn)


async def get_db() -> AsyncIterator[asyncpg.Connection]:
    async with _acquire_connection() as conn:
        yield conn


async def get_db_connection() -> asyncpg.Connection:
    """
    Use with caution in background tasks. Caller must release using release_db_connection.
    """
    if _pool is None:
        await create_pool()
    assert _pool is not None
    return await _pool.acquire()


async def release_db_connection(conn: asyncpg.Connection) -> None:
    if _pool is None:
        return
    await _pool.release(conn)


async def _ensure_schema_initialized(pool: asyncpg.Pool) -> None:
    """
    Ensure required tables exist. If `users` table is missing, apply full schema.sql.
    """
    if not settings.AUTO_APPLY_SCHEMA:
        return

    async with pool.acquire() as conn:
        users_table = await conn.fetchval("SELECT to_regclass('public.users')")
        if users_table:
            return

        if not SCHEMA_PATH.exists():
            raise RuntimeError(f"Schema file not found at {SCHEMA_PATH}")

        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        try:
            await conn.execute(schema_sql)
        except Exception as exc:
            raise RuntimeError(
                "Database schema initialization failed. "
                "Run `psql \"$DATABASE_URL\" -f backend/database/schema.sql` manually. "
                f"Original error: {exc}"
            ) from exc
