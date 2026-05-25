from __future__ import annotations

import json

from src.plugins.base import Plugin, ToolDefinition
from plugins.builtin.homeassistant.service import HomeAssistantService


class HomeAssistantPlugin(Plugin):
    name = "homeassistant"
    display_name = "Home Assistant"
    version = "0.1.0"
    description = "Control Home Assistant entities: lights, switches, sensors."
    config_key = "homeassistant"

    def __init__(self):
        self.service: HomeAssistantService | None = None

    async def setup(self, config: dict) -> None:
        self.service = HomeAssistantService(
            host=config.get("host", "http://homeassistant.local:8123"),
            token=config.get("token", ""),
        )

    async def health_check(self) -> bool:
        return await self.service.health_check()

    def get_tools(self) -> list[ToolDefinition]:
        schema = {
            "type": "function",
            "function": {
                "name": "homeassistant_call_service",
                "description": "Control Home Assistant entities. Toggle lights, switches, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Home Assistant entity ID, e.g. 'light.living_room'",
                        },
                        "service": {
                            "type": "string",
                            "description": "Service to call: toggle, turn_on, turn_off, etc.",
                            "default": "toggle",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Domain (inferred from entity_id if omitted)",
                        },
                        "data": {
                            "type": "object",
                            "description": "Additional service data",
                        },
                    },
                    "required": ["entity_id"],
                },
            },
        }

        async def handler(
            entity_id: str,
            service: str = "toggle",
            domain: str | None = None,
            data: dict | None = None,
            **kwargs,
        ) -> str:
            if domain is None:
                domain = entity_id.split(".")[0]
            result = await self.service.call_service(domain, service, entity_id, data or {})
            return json.dumps(result)

        return [ToolDefinition(schema=schema, handler=handler)]

    async def teardown(self) -> None:
        if self.service:
            await self.service.close()


PLUGIN_CLASS = HomeAssistantPlugin