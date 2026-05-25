from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger()


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
        resp = await self.client.get(f"{self.host}/api/states/{entity_id}")
        resp.raise_for_status()
        return resp.json()

    async def call_service(
        self, domain: str, service: str, entity_id: str, data: dict | None = None
    ) -> dict:
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