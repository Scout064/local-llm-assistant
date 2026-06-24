from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite

from src.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'New conversation',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    tool_name       TEXT,
    tool_call_json  TEXT,
    image_paths     TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, created_at);
"""

_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()


async def init_db() -> aiosqlite.Connection:
    global _db
    async with _db_lock:
        if _db is not None:
            return _db
        db_path = Path(settings.persistence.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(str(db_path))
        _db.row_factory = aiosqlite.Row
        await _db.executescript(_SCHEMA)
        await _db.commit()
        return _db


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is not None:
        return _db
    async with _db_lock:
        if _db is None:
            await init_db()
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None