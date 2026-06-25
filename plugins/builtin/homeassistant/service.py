from __future__ import annotations

import re

import httpx
import structlog

from src.plugins.base import Plugin, ToolDefinition

log = structlog.get_logger()

_ENTITY_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
_DOMAIN_RE = re.compile(r"^[a-z_]+$")
_SERVICE_RE = re.compile(r"^[a-z_]+$")


class HomeAssistantService:
    def __init__(self, host: str, token: str):
        self.host = host.rstrip("/")
        self.token = token
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def health_check(self) -> bool:
        try:
            resp = await self.client.get(f"{self.host}/api/")
            return resp.status_code == 200
        except Exception:
            return False

    async def get_entity_state(self, entity_id: str) -> dict:
        if not _ENTITY_RE.match(entity_id):
            raise ValueError(f"Invalid entity_id: {entity_id}")
        resp = await self.client.get(f"{self.host}/api/states/{entity_id}")
        resp.raise_for_status()
        return resp.json()

    async def call_service(
        self, domain: str, service: str, entity_id: str, data: dict | None = None
    ) -> dict:
        if not _DOMAIN_RE.match(domain):
            raise ValueError(f"Invalid domain: {domain}")
        if not _SERVICE_RE.match(service):
            raise ValueError(f"Invalid service: {service}")
        if entity_id and not _ENTITY_RE.match(entity_id):
            raise ValueError(f"Invalid entity_id: {entity_id}")
        payload = {"entity_id": entity_id}
        if data:
            payload.update(data)
        resp = await self.client.post(
            f"{self.host}/api/services/{domain}/{service}",
            json=payload,
        )
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status": "ok"}

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()