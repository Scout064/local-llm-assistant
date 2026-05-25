from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

import ollama
import structlog

from src.config import settings

logger = structlog.get_logger()


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class AgentEvent:
    type: str
    tool: str | None = None
    result: str | None = None


Event = str | ToolCall | AgentEvent


class OllamaClient:
    def __init__(self):
        self._client: ollama.AsyncClient | None = None

    @property
    def client(self) -> ollama.AsyncClient:
        if self._client is None:
            self._client = ollama.AsyncClient(host=settings.llm.host)
        return self._client

    async def check_model_available(self) -> bool:
        try:
            models = await self.client.list()
            model_names = [m.model for m in models.models]
            configured = settings.llm.model
            if configured not in model_names:
                for name in model_names:
                    if name.startswith(configured.split(":")[0]):
                        logger.warning("model_variant_found", configured=configured, available=name)
                        return True
                logger.error(
                    "model_not_found",
                    configured=configured,
                    available=model_names,
                    hint=f"Run: ollama pull {configured}",
                )
                return False
            return True
        except Exception as e:
            logger.error("model_check_failed", error=str(e))
            return False

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[Event]:
        kwargs: dict[str, Any] = {
            "model": settings.llm.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        response = await self.client.chat(**kwargs)
        async for chunk in response:
            if chunk.message.content:
                yield chunk.message.content

            if chunk.message.tool_calls:
                for tc in chunk.message.tool_calls:
                    yield ToolCall(
                        name=tc.function.name,
                        arguments=tc.function.arguments or {},
                    )

    async def chat_no_stream(
        self,
        messages: list[dict],
    ) -> str:
        response = await self.client.chat(
            model=settings.llm.model,
            messages=messages,
            stream=False,
        )
        return response.message.content or ""


ollama_client = OllamaClient()