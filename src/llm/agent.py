from __future__ import annotations

import json
from typing import AsyncIterator

import structlog

from src.config import settings
from src.llm.client import OllamaClient, AgentEvent, ToolCall, ollama_client
from src.plugins.registry import PluginRegistry
from src.persistence.conversations import (
    add_message,
    get_messages,
    update_conversation_title,
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
                tool_call_data = json.loads(msg["tool_call_json"])
                messages.append({
                    "role": "assistant",
                    "content": msg["content"] or "",
                    "tool_calls": [tool_call_data],
                })
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
        messages = [system_msg] + messages[-(max_history):]

    tool_schemas = registry.get_ollama_tool_schemas()
    ollama_tools = tool_schemas if tool_schemas else None

    needs_title = len([m for m in raw_messages if m["role"] == "user"]) == 1

    max_iterations = 10
    for _ in range(max_iterations):
        text_in_this_turn = ""
        tool_call = None

        async for item in client.chat_stream(messages, tools=ollama_tools):
            if isinstance(item, str):
                text_in_this_turn += item
                yield item
            elif isinstance(item, ToolCall):
                tool_call = item
                break

        if text_in_this_turn:
            await add_message(conversation_id, "assistant", text_in_this_turn)

        if tool_call is None:
            break

        # Execute tool
        yield AgentEvent("tool_start", tool=tool_call.name)

        handler = registry.get_tool_handler(tool_call.name)
        if handler is None:
            result = f"Error: tool '{tool_call.name}' not found"
        else:
            try:
                result = await handler(**tool_call.arguments)
            except Exception as exc:
                result = f"Error: {exc}"

        yield AgentEvent("tool_done", tool=tool_call.name, result=result)

        # Inject result and continue
        await add_message(conversation_id, "tool", str(result), tool_name=tool_call.name)
        messages.append({"role": "tool", "content": str(result), "name": tool_call.name})

        tool_call_json = json.dumps({
            "function": {"name": tool_call.name, "arguments": tool_call.arguments}
        })
        await add_message(
            conversation_id,
            "assistant",
            text_in_this_turn or "",
            tool_call_json=tool_call_json,
        )

    if needs_title:
        await _auto_title(conversation_id, user_message, client)


async def _auto_title(conversation_id: str, user_message: str, client: OllamaClient):
    title_messages = [
        {"role": "system", "content": "Generate a 4-6 word title for this conversation. Reply with ONLY the title, no punctuation."},
        {"role": "user", "content": user_message},
    ]
    title = await client.chat_no_stream(title_messages)
    title = title.strip().strip('"').strip("'")
    if title:
        await update_conversation_title(conversation_id, title)
        return title
    return None