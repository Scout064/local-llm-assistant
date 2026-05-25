from __future__ import annotations

import json

from src.plugins.base import ToolDefinition


def generate_image_tool(plugin):
    lora_descriptions = ", ".join(
        f'"{l["alias"]}"' for l in plugin.loras
    ) if plugin.loras else '"none"'

    schema = {
        "type": "function",
        "function": {
            "name": "comfyui_generate_image",
            "description": (
                "Generate an image using ComfyUI. Use when the user requests an image, "
                "or when a visual would meaningfully enhance the conversation. "
                "Choose a LoRA style if one fits the request."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Detailed positive prompt",
                    },
                    "negative_prompt": {
                        "type": "string",
                        "default": "blurry, low quality, watermark",
                    },
                    "workflow_name": {
                        "type": "string",
                        "description": "Workflow alias from settings (e.g. 'default', 'flux'). Omit to use default.",
                        "default": "default",
                    },
                    "lora_alias": {
                        "type": "string",
                        "description": f"LoRA style alias from settings. Options: {lora_descriptions}. Use 'none' for no LoRA.",
                        "default": "none",
                    },
                    "lora_strength": {
                        "type": "number",
                        "description": "LoRA strength, 0.0-1.5. Default 1.0.",
                        "default": 1.0,
                    },
                    "width": {"type": "integer", "default": 1024},
                    "height": {"type": "integer", "default": 1024},
                    "steps": {"type": "integer", "default": 20},
                    "cfg": {"type": "number", "default": 7.0},
                },
                "required": ["prompt"],
            },
        },
    }

    async def handler(
        prompt: str,
        negative_prompt: str = "blurry, low quality, watermark",
        workflow_name: str = "default",
        lora_alias: str = "none",
        lora_strength: float = 1.0,
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        cfg: float = 7.0,
        **kwargs,
    ) -> str:
        workflow_path = plugin.workflows.get(workflow_name, plugin.workflows.get("default"))
        if workflow_path is None:
            return json.dumps({"error": f"Workflow '{workflow_name}' not found"})

        workflow = plugin.service.load_workflow(workflow_path)

        lora_filename = ""
        for lora in plugin.loras:
            if lora["alias"] == lora_alias:
                lora_filename = lora["filename"]
                break

        result = await plugin.service.generate_image(
            workflow=workflow,
            node_map=plugin.node_map,
            prompt=prompt,
            negative_prompt=negative_prompt,
            lora_filename=lora_filename,
            lora_strength=lora_strength,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
        )
        return result

    return ToolDefinition(schema=schema, handler=handler)