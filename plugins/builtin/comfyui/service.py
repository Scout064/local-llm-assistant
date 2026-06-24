from __future__ import annotations

import asyncio
import copy
import json
import random
import time
from pathlib import Path
from uuid import uuid4

import httpx
import structlog

log = structlog.get_logger()


class ComfyUIService:
    def __init__(self, host: str, output_dir: str):
        self.host = host.rstrip("/")
        self.output_dir = Path(output_dir)
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=300.0)
        return self._client

    async def health_check(self) -> bool:
        try:
            resp = await self.client.get(f"{self.host}/system_stats")
            return resp.status_code == 200
        except Exception:
            return False

    def load_workflow(self, workflow_path: str) -> dict:
        path = Path(workflow_path)
        if not path.exists():
            raise FileNotFoundError(f"Workflow file not found: {path}")
        return json.loads(path.read_text())

    @staticmethod
    def patch_workflow(workflow: dict, node_map: dict, params: dict) -> dict:
        wf = copy.deepcopy(workflow)

        fields = {
            "positive_prompt": (["text"], params.get("prompt")),
            "negative_prompt": (["text"], params.get("negative_prompt")),
            "sampler":         (["steps"], params.get("steps")),
        }

        for map_key, (input_keys, value) in fields.items():
            if map_key in node_map and value is not None:
                node = wf[node_map[map_key]]["inputs"]
                for k in input_keys:
                    node[k] = value

        if "latent_image" in node_map:
            latent_inputs = wf[node_map["latent_image"]]["inputs"]
            if params.get("width") is not None:
                latent_inputs["width"] = params["width"]
            if params.get("height") is not None:
                latent_inputs["height"] = params["height"]

        if "sampler" in node_map:
            sampler_inputs = wf[node_map["sampler"]]["inputs"]
            if "steps" in params:
                sampler_inputs["steps"] = params["steps"]
            if "cfg" in params:
                sampler_inputs["cfg"] = params["cfg"]
            if "seed" in params:
                sampler_inputs["seed"] = params["seed"]
            else:
                sampler_inputs["seed"] = random.randint(0, 2**32 - 1)

        if "lora_loader" in node_map:
            lora_inputs = wf[node_map["lora_loader"]]["inputs"]
            lora_filename = params.get("lora_filename", "")
            lora_inputs["lora_name"] = lora_filename
            default_strength = 1.0 if lora_filename else 0.0
            lora_inputs["strength_model"] = params.get("lora_strength", default_strength)
            lora_inputs["strength_clip"] = params.get("lora_strength", default_strength)

        return wf

    async def generate_image(
        self,
        workflow: dict,
        node_map: dict,
        prompt: str,
        negative_prompt: str = "blurry, low quality, watermark",
        lora_filename: str = "",
        lora_strength: float = 1.0,
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        cfg: float = 7.0,
    ) -> str:
        params = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
            "lora_filename": lora_filename,
            "lora_strength": lora_strength,
        }

        patched = self.patch_workflow(workflow, node_map, params)

        client_id = str(uuid4())
        prompt_resp = await self.client.post(
            f"{self.host}/prompt",
            json={"prompt": patched, "client_id": client_id},
        )
        prompt_data = prompt_resp.json()
        prompt_id = prompt_data["prompt_id"]

        for _ in range(120):
            await asyncio.sleep(0.5)
            history_resp = await self.client.get(f"{self.host}/history/{prompt_id}")
            history = history_resp.json()
            if prompt_id in history:
                break
        else:
            raise TimeoutError(f"ComfyUI prompt {prompt_id} timed out")

        outputs = history[prompt_id]["outputs"]

        for node_id, node_output in outputs.items():
            if "images" in node_output:
                for image_info in node_output["images"]:
                    filename = image_info["filename"]
                    subfolder = image_info.get("subfolder", "")
                    img_type = image_info.get("type", "output")

                    view_url = (
                        f"{self.host}/view?"
                        f"filename={filename}&subfolder={subfolder}&type={img_type}"
                    )

                    saved_path = await self._download_image(view_url, prompt_id, filename)
                    if saved_path:
                        return json.dumps({
                            "type": "image",
                            "path": f"/output/images/{saved_path.name}",
                            "prompt": prompt,
                        })

        raise RuntimeError("No images found in ComfyUI output")

    async def _download_image(self, url: str, prompt_id: str, filename: str) -> Path | None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for attempt in range(5):
            try:
                resp = await self.client.get(url)
                if resp.status_code == 200 and len(resp.content) > 0:
                    timestamp = int(time.time())
                    ext = Path(filename).suffix or ".png"
                    save_name = f"{timestamp}_{prompt_id[:8]}{ext}"
                    save_path = self.output_dir / save_name
                    save_path.write_bytes(resp.content)
                    return save_path
            except Exception as e:
                log.warning("image_download_retry", attempt=attempt, error=str(e))
            await asyncio.sleep(0.2)
        return None