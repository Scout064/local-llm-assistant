from __future__ import annotations

import json

from src.plugins.base import Plugin, ToolDefinition
from plugins.builtin.proxmox.service import ProxmoxService


class ProxmoxPlugin(Plugin):
    name = "proxmox"
    display_name = "Proxmox VE"
    version = "0.1.0"
    description = "Manage Proxmox VMs and containers: list, status, start, stop."
    config_key = "proxmox"

    def __init__(self):
        self.service: ProxmoxService | None = None

    async def setup(self, config: dict) -> None:
        self.service = ProxmoxService(
            host=config.get("host", "https://proxmox.local:8006"),
            user=config.get("user", "root@pam"),
            token_name=config.get("token_name", ""),
            token_value=config.get("token_value", ""),
            verify_ssl=config.get("verify_ssl", False),
        )

    async def health_check(self) -> bool:
        return await self.service.health_check()

    def get_tools(self) -> list[ToolDefinition]:
        schema = {
            "type": "function",
            "function": {
                "name": "proxmox_vm_action",
                "description": "Check or manage Proxmox VMs. List VMs, get status, start or stop VMs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "status", "start", "stop"],
                            "description": "Action to perform",
                            "default": "list",
                        },
                        "vmid": {
                            "type": "integer",
                            "description": "VM ID (required for status, start, stop actions)",
                        },
                    },
                    "required": [],
                },
            },
        }

        async def handler(
            action: str = "list",
            vmid: int | None = None,
            **kwargs,
        ) -> str:
            if action == "list":
                vms = await self.service.list_vms()
                return json.dumps(vms, default=str)
            elif action == "status" and vmid is not None:
                status = await self.service.get_vm_status(vmid)
                return json.dumps(status, default=str)
            elif action == "start" and vmid is not None:
                return await self.service.start_vm(vmid)
            elif action == "stop" and vmid is not None:
                return await self.service.stop_vm(vmid)
            return json.dumps({"error": "invalid action or missing vmid"})

        return [ToolDefinition(schema=schema, handler=handler)]


PLUGIN_CLASS = ProxmoxPlugin