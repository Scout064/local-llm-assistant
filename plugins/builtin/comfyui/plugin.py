from __future__ import annotations

from src.plugins.base import Plugin, ToolDefinition
from plugins.builtin.comfyui.service import ComfyUIService


class ComfyUIPlugin(Plugin):
    name = "comfyui"
    display_name = "ComfyUI Image Generation"
    version = "0.1.0"
    description = "Generate images using ComfyUI workflows with LoRA support."
    config_key = "comfyui"

    def __init__(self):
        self.service: ComfyUIService | None = None
        self.workflows: dict[str, str] = {}
        self.node_map: dict[str, str] = {}
        self.loras: list[dict] = []

    async def setup(self, config: dict) -> None:
        self.service = ComfyUIService(
            host=config.get("host", "http://localhost:8188"),
            output_dir=config.get("output_dir", "./output/images"),
        )
        self.workflows = config.get("workflows", {"default": "plugins/builtin/comfyui/workflows/default_txt2img.json"})
        self.node_map = config.get("node_map", {})
        self.loras = config.get("loras", [])

    async def health_check(self) -> bool:
        return await self.service.health_check()

    def get_tools(self) -> list[ToolDefinition]:
        from plugins.builtin.comfyui.tools import generate_image_tool
        return [generate_image_tool(self)]

    async def teardown(self) -> None:
        if self.service and self.service._client:
            await self.service._client.aclose()


PLUGIN_CLASS = ComfyUIPlugin