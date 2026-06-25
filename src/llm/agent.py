from __future__ import annotations

import json
import re
from typing import AsyncIterator

import structlog

from src.config import settings
from src.llm.client import OllamaClient, AgentEvent, ToolCall, ollama_client
from src.plugins.registry import PluginRegistry
from src.persistence.conversations import (
    add_message,
    get_messages,
    update_conversation_title,
    get_conversation,
)

logger = structlog.get_logger()


async def run(
    conversation_id: str,
    user_message: str,
    registry: PluginRegistry,
    client: OllamaClient | None = None,
) -> AsyncIterator[str | AgentEvent]:
    if client is None:
        client = ollama_client

    await add_message(conversation_id, "user", user_message)

    raw_messages = await get_messages(conversation_id)

    messages = [{"role": "system", "content": settings.llm.system_prompt}]
    for msg in raw_messages:
        if msg["role"] == "user":
            messages.append({"role": "user", "content": msg["content"]})
        elif msg["role"] == "assistant":
            if msg.get("tool_call_json"):
                try:
                    tool_call_data = json.loads(msg["tool_call_json"])
                    messages.append({
                        "role": "assistant",
                        "content": msg["content"] or "",
                        "tool_calls": [tool_call_data],
                    })
                except (json.JSONDecodeError, TypeError):
                    logger.warning("malformed_tool_call_json", msg_id=msg["id"])
                    messages.append({"role": "assistant", "content": msg["content"] or ""})
            else:
                messages.append({"role": "assistant", "content": msg["content"]})
        elif msg["role"] == "tool":
            messages.append({
                "role": "tool",
                "content": msg["content"],
                "name": msg["tool_name"],
            })

    max_history = settings.llm.max_history_messages
    if len(messages) > max_history + 1:
        system_msg = messages[0]
        trimmed = messages[-(max_history):]
        while trimmed and trimmed[0].get("role") == "tool":
            trimmed = trimmed[1:]
        while trimmed and trimmed[-1].get("tool_calls") and not trimmed[-1].get("content"):
            trimmed = trimmed[:-1]
        messages = [system_msg] + trimmed

    tool_schemas = registry.get_ollama_tool_schemas()
    ollama_tools = tool_schemas if tool_schemas else None

    conv = await get_conversation(conversation_id)
    needs_title = (
        len([m for m in raw_messages if m["role"] == "user"]) == 1
        and conv is not None
        and conv["title"] == "New conversation"
    )

    max_iterations = 10
    for _ in range(max_iterations):
        text_in_this_turn = ""
        tool_calls_in_turn: list[ToolCall] = []

        async for item in client.chat_stream(messages, tools=ollama_tools):
            if isinstance(item, str):
                text_in_this_turn += item
                yield item
            elif isinstance(item, ToolCall):
                tool_calls_in_turn.append(item)

        if not tool_calls_in_turn:
            if text_in_this_turn:
                await add_message(conversation_id, "assistant", text_in_this_turn)
            break

        for tc in tool_calls_in_turn:
            yield AgentEvent("tool_start", tool=tc.name)

            handler = registry.get_tool_handler(tc.name)
            if handler is None:
                result = f"Error: tool '{tc.name}' not found"
            else:
                try:
                    result = await handler(**tc.arguments)
                except Exception as exc:
                    result = f"Error: {exc}"

            yield AgentEvent("tool_done", tool=tc.name, result=result)

            tool_call_json = json.dumps({
                "function": {"name": tc.name, "arguments": tc.arguments}
            })
            await add_message(
                conversation_id, "assistant",
                text_in_this_turn or "",
                tool_call_json=tool_call_json,
            )
            await add_message(conversation_id, "tool", str(result), tool_name=tc.name)

            messages.append({
                "role": "assistant",
                "content": text_in_this_turn or "",
                "tool_calls": [{"function": {"name": tc.name, "arguments": tc.arguments}}],
            })
            messages.append({"role": "tool", "content": str(result), "name": tc.name})
            text_in_this_turn = ""

    else:
        msg = "[Assistant reached maximum tool-call depth and stopped.]"
        await add_message(conversation_id, "assistant", msg)
        yield msg

    if needs_title:
        await _auto_title(conversation_id, user_message, client)


async def _auto_title(conversation_id: str, user_message: str, client: OllamaClient):
    title_messages = [
        {"role": "system", "content": "Generate a 4-6 word title for this conversation. Reply with ONLY the title, no punctuation."},
        {"role": "user", "content": user_message},
    ]
    title = await client.chat_no_stream(title_messages)
    title = re.sub(r"[*_#`\n\r\t]+", " ", title).strip().strip('"').strip("'").strip()
    if title:
        await update_conversation_title(conversation_id, title)
        from src.web.routes import broadcast_global
        await broadcast_global({"type": "conversation_titled", "id": conversation_id, "title": title})
        return title
    return None