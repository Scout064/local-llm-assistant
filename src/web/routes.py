from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Set

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.llm.agent import run
from src.llm.client import AgentEvent
from src.plugins.registry import PluginRegistry
from src.persistence.conversations import (
    create_conversation,
    get_conversation,
    list_conversations,
    update_conversation_title,
    soft_delete_conversation,
    get_messages,
    add_message,
)

logger = structlog.get_logger()

router = APIRouter()

websocket_connections: dict[str, Set[WebSocket]] = defaultdict(set)

STATIC_DIR = Path(__file__).parent / "static"


def _get_registry(request: Request) -> PluginRegistry:
    return request.app.state.registry


@router.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text()


@router.get("/conversations")
async def api_list_conversations():
    convs = await list_conversations(include_deleted=False)
    return convs


@router.post("/conversations")
async def api_create_conversation(request: Request):
    body = await request.json() if await request.body() else {}
    title = body.get("title", "New conversation")
    conv_id = await create_conversation(title=title)
    conv = await get_conversation(conv_id)
    await broadcast_global({"type": "conversation_created", "id": conv_id, "title": title})
    return conv


@router.put("/conversations/{conversation_id}/title")
async def api_update_title(conversation_id: str, request: Request):
    body = await request.json()
    title = body.get("title", "New conversation")
    await update_conversation_title(conversation_id, title)
    await broadcast_global({"type": "conversation_titled", "id": conversation_id, "title": title})
    return {"status": "ok"}


@router.delete("/conversations/{conversation_id}")
async def api_delete_conversation(conversation_id: str):
    await soft_delete_conversation(conversation_id)
    return {"status": "ok"}


@router.get("/conversations/{conversation_id}/messages")
async def api_get_messages(conversation_id: str):
    msgs = await get_messages(conversation_id)
    return msgs


@router.get("/plugins")
async def api_plugins(request: Request):
    registry = _get_registry(request)
    return registry.get_status()


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    await websocket.accept()
    websocket_connections[conversation_id].add(websocket)
    registry = _get_registry(websocket.app)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type")

            if msg_type == "message":
                text = msg.get("text", "")
                await broadcast(conversation_id, {"type": "status", "state": "THINKING"})

                async for event in run(conversation_id, text, registry):
                    if isinstance(event, str):
                        await broadcast(conversation_id, {"type": "chunk", "text": event})
                    elif isinstance(event, AgentEvent):
                        if event.type == "tool_start":
                            await broadcast(conversation_id, {"type": "tool_start", "tool": event.tool})
                        elif event.type == "tool_done":
                            await broadcast(conversation_id, {"type": "tool_done", "tool": event.tool})
                            try:
                                result_data = json.loads(event.result) if event.result else {}
                                if isinstance(result_data, dict) and result_data.get("type") == "image":
                                    await broadcast(conversation_id, {
                                        "type": "image",
                                        "path": result_data.get("path", ""),
                                        "prompt": result_data.get("prompt", ""),
                                    })
                            except (json.JSONDecodeError, TypeError):
                                pass

                await broadcast(conversation_id, {"type": "done"})
                await broadcast(conversation_id, {"type": "status", "state": "IDLE"})

            elif msg_type == "voice_start":
                await broadcast(conversation_id, {"type": "status", "state": "LISTENING"})

            elif msg_type == "new_conversation":
                conv_id = await create_conversation()
                conv = await get_conversation(conv_id)
                await websocket.send_json({
                    "type": "conversation_created",
                    "id": conv_id,
                    "title": conv["title"],
                })

            elif msg_type == "clear_history":
                await _clear_conversation_messages(conversation_id)
                await websocket.send_json({"type": "history_cleared"})

    except WebSocketDisconnect:
        websocket_connections[conversation_id].discard(websocket)
    except Exception as e:
        logger.error("websocket_error", error=str(e))
        websocket_connections[conversation_id].discard(websocket)


async def _clear_conversation_messages(conversation_id: str):
    from src.persistence.db import get_db
    db = await get_db()
    await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    await db.commit()


async def broadcast(conversation_id: str, message: dict):
    for ws in list(websocket_connections.get(conversation_id, set())):
        try:
            await ws.send_json(message)
        except Exception:
            websocket_connections[conversation_id].discard(ws)


async def broadcast_global(message: dict):
    for ws_set in websocket_connections.values():
        for ws in ws_set:
            try:
                await ws.send_json(message)
            except Exception:
                pass


@router.get("/output/images/{filename}")
async def serve_image(filename: str):
    image_path = Path(settings.plugins.comfyui.output_dir) / filename
    if not image_path.exists():
        return {"error": "not found"}
    return FileResponse(str(image_path), media_type="image/png")