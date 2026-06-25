import copy
import json

import pytest

from plugins.builtin.comfyui.service import ComfyUIService


SAMPLE_WORKFLOW = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 123,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["10", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
        "_meta": {"title": "KSampler"},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        "_meta": {"title": "EmptyLatentImage"},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "default positive", "clip": ["10", 1]},
        "_meta": {"title": "Positive Prompt"},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "default negative", "clip": ["10", 1]},
        "_meta": {"title": "Negative Prompt"},
    },
    "10": {
        "class_type": "LoraLoader",
        "inputs": {
            "lora_name": "",
            "strength_model": 1.0,
            "strength_clip": 1.0,
            "model": ["4", 0],
            "clip": ["4", 1],
        },
        "_meta": {"title": "LoRA Loader"},
    },
}

NODE_MAP_WITH_LORA = {
    "positive_prompt": "6",
    "negative_prompt": "7",
    "sampler": "3",
    "latent_image": "5",
    "lora_loader": "10",
}

NODE_MAP_NO_LORA = {
    "positive_prompt": "6",
    "negative_prompt": "7",
    "sampler": "3",
    "latent_image": "5",
}


class TestPatchWorkflow:
    def test_patch_prompt(self):
        result = ComfyUIService.patch_workflow(
            SAMPLE_WORKFLOW, NODE_MAP_WITH_LORA, {"prompt": "a beautiful cat"}
        )
        assert result["6"]["inputs"]["text"] == "a beautiful cat"
        assert result["7"]["inputs"]["text"] == "default negative"

    def test_patch_negative_prompt(self):
        result = ComfyUIService.patch_workflow(
            SAMPLE_WORKFLOW,
            NODE_MAP_WITH_LORA,
            {"prompt": "cat", "negative_prompt": "blurry"},
        )
        assert result["7"]["inputs"]["text"] == "blurry"

    def test_patch_sampler_params(self):
        result = ComfyUIService.patch_workflow(
            SAMPLE_WORKFLOW,
            NODE_MAP_WITH_LORA,
            {"prompt": "cat", "steps": 30, "cfg": 8.5},
        )
        assert result["3"]["inputs"]["steps"] == 30
        assert result["3"]["inputs"]["cfg"] == 8.5

    def test_patch_latent_dimensions(self):
        result = ComfyUIService.patch_workflow(
            SAMPLE_WORKFLOW,
            NODE_MAP_WITH_LORA,
            {"prompt": "cat", "width": 512, "height": 768},
        )
        assert result["5"]["inputs"]["width"] == 512
        assert result["5"]["inputs"]["height"] == 768

    def test_patch_lora_with_filename(self):
        result = ComfyUIService.patch_workflow(
            SAMPLE_WORKFLOW,
            NODE_MAP_WITH_LORA,
            {"prompt": "cat", "lora_filename": "add_detail.safetensors", "lora_strength": 0.8},
        )
        assert result["10"]["inputs"]["lora_name"] == "add_detail.safetensors"
        assert result["10"]["inputs"]["strength_model"] == 0.8
        assert result["10"]["inputs"]["strength_clip"] == 0.8

    def test_patch_lora_without_filename(self):
        result = ComfyUIService.patch_workflow(
            SAMPLE_WORKFLOW,
            NODE_MAP_WITH_LORA,
            {"prompt": "cat", "lora_filename": ""},
        )
        assert result["10"]["inputs"]["lora_name"] == ""
        assert result["10"]["inputs"]["strength_model"] == 0.0
        assert result["10"]["inputs"]["strength_clip"] == 0.0

    def test_no_lora_node_skips_lora(self):
        result = ComfyUIService.patch_workflow(
            SAMPLE_WORKFLOW,
            NODE_MAP_NO_LORA,
            {"prompt": "cat", "lora_filename": "add_detail.safetensors"},
        )
        assert "10" not in NODE_MAP_NO_LORA
        assert result["6"]["inputs"]["text"] == "cat"

    def test_does_not_mutate_original(self):
        original = copy.deepcopy(SAMPLE_WORKFLOW)
        ComfyUIService.patch_workflow(
            SAMPLE_WORKFLOW, NODE_MAP_WITH_LORA, {"prompt": "cat"}
        )
        assert SAMPLE_WORKFLOW == original


class TestLoraAliasResolution:
    def test_alias_resolution_from_settings(self):
        from src.config import settings

        loras = settings.plugins.comfyui.loras
        alias_map = {lora.alias: lora.filename for lora in loras}

        assert "none" in alias_map
        assert alias_map["none"] == ""
        assert "detail" in alias_map
        assert alias_map["detail"] == "add_detail.safetensors"

    def test_none_alias_produces_empty_filename(self):
        from src.config import settings

        loras = settings.plugins.comfyui.loras
        result = ""
        for lora in loras:
            if lora.alias == "none":
                result = lora.filename
                break
        assert result == ""


class TestPatchWorkflowEdgeCases:
    def test_width_and_height_both_applied(self):
        """Ensure both width AND height are patched (regression for duplicate key bug)."""
        result = ComfyUIService.patch_workflow(
            SAMPLE_WORKFLOW,
            NODE_MAP_WITH_LORA,
            {"prompt": "test", "width": 640, "height": 480},
        )
        assert result["5"]["inputs"]["width"] == 640
        assert result["5"]["inputs"]["height"] == 480

    def test_only_width_specified(self):
        result = ComfyUIService.patch_workflow(
            SAMPLE_WORKFLOW,
            NODE_MAP_WITH_LORA,
            {"prompt": "test", "width": 512},
        )
        assert result["5"]["inputs"]["width"] == 512
        assert result["5"]["inputs"]["height"] == 1024  # unchanged

    def test_seed_generated_when_not_specified(self):
        result = ComfyUIService.patch_workflow(
            SAMPLE_WORKFLOW,
            NODE_MAP_WITH_LORA,
            {"prompt": "test"},
        )
        assert isinstance(result["3"]["inputs"]["seed"], int)