from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from src.persistence.db import get_db


async def create_conversation(title: str = "New conversation") -> str:
    db = await get_db()
    conv_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (conv_id, title, now, now),
    )
    await db.commit()
    return conv_id


async def get_conversation(conversation_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


async def list_conversations(include_deleted: bool = False) -> list[dict]:
    db = await get_db()
    if include_deleted:
        cursor = await db.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC"
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM conversations WHERE deleted_at IS NULL ORDER BY updated_at DESC"
        )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def update_conversation_title(conversation_id: str, title: str) -> None:
    title = title[:256].strip()
    if not title:
        title = "New conversation"
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title, now, conversation_id),
    )
    await db.commit()


async def soft_delete_conversation(conversation_id: str) -> None:
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE conversations SET deleted_at = ?, updated_at = ? WHERE id = ?",
        (now, now, conversation_id),
    )
    await db.commit()


async def add_message(
    conversation_id: str,
    role: str,
    content: str,
    tool_name: str | None = None,
    tool_call_json: str | None = None,
    image_paths: list[str] | None = None,
) -> str:
    db = await get_db()
    msg_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    paths_json = json.dumps(image_paths) if image_paths else None
    await db.execute(
        "INSERT INTO messages (id, conversation_id, role, content, tool_name, tool_call_json, image_paths, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (msg_id, conversation_id, role, content, tool_name, tool_call_json, paths_json, now),
    )
    await db.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (now, conversation_id),
    )
    await db.commit()
    return msg_id


async def get_messages(conversation_id: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]