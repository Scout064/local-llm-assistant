from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings

_log = structlog.get_logger()


def _load_yaml() -> dict:
    yaml_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
    if not yaml_path.exists():
        return {}
    with open(yaml_path) as f:
        raw = yaml.safe_load(f) or {}
    return _substitute_env(raw)


def _substitute_env(obj):
    if isinstance(obj, str):
        def replacer(m):
            var_name = m.group(1)
            value = os.environ.get(var_name)
            if value is None:
                _log.warning("env_var_not_set", variable=var_name)
                return ""
            return value
        return re.sub(r"\$\{(\w+)\}", replacer, obj)
    if isinstance(obj, dict):
        return {k: _substitute_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_env(item) for item in obj]
    return obj


class WakeWordSettings(BaseModel):
    enabled: bool = True
    model: str = "hey_jarvis"
    threshold: float = 0.5
    listen_timeout: float = 15.0


class VoiceSettings(BaseModel):
    enabled: bool = True
    input_device: int | str | None = None
    output_device: int | str | None = None
    wake_word: WakeWordSettings = WakeWordSettings()
    stt_model: str = "large-v3"
    stt_device: str = "cuda:0"
    tts_backend: str = "kokoro"
    tts_voice: str = "af_heart"
    vad_threshold: float = 0.5
    silence_ms: int = 800


class LLMSettings(BaseModel):
    host: str = "http://localhost:11434"
    model: str = "qwen2.5:14b"
    system_prompt: str = "You are a capable local assistant."
    context_window: int = 8192
    temperature: float = 0.7
    max_history_messages: int = 40


class LoraEntry(BaseModel):
    alias: str = ""
    filename: str = ""


class ComfyUISettings(BaseModel):
    host: str = "http://localhost:8188"
    output_dir: str = "./output/images"
    workflows: dict[str, str] = {"default": "plugins/builtin/comfyui/workflows/default_txt2img.json"}
    node_map: dict[str, str] = {}
    loras: list[LoraEntry] = []


class HomeAssistantSettings(BaseModel):
    host: str = "http://homeassistant.local:8123"
    token: str = ""


class ProxmoxSettings(BaseModel):
    host: str = "https://proxmox.local:8006"
    user: str = "root@pam"
    token_name: str = ""
    token_value: str = ""
    verify_ssl: bool = False


class GoogleDriveSettings(BaseModel):
    credentials_file: str = "~/.config/assistant/gdrive_credentials.json"
    token_file: str = "~/.config/assistant/gdrive_token.json"


class PluginSettings(BaseModel):
    extra_dirs: list[str] = ["./plugins/community"]
    disabled: list[str] = []
    comfyui: ComfyUISettings = ComfyUISettings()
    homeassistant: HomeAssistantSettings = HomeAssistantSettings()
    proxmox: ProxmoxSettings = ProxmoxSettings()
    google_drive: GoogleDriveSettings = GoogleDriveSettings()


class PersistenceSettings(BaseModel):
    db_path: str = "./data/conversations.db"


class WebSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 7860
    log_level: str = "info"
    api_key: str = ""


class Settings(BaseSettings):
    llm: LLMSettings = LLMSettings()
    voice: VoiceSettings = VoiceSettings()
    plugins: PluginSettings = PluginSettings()
    persistence: PersistenceSettings = PersistenceSettings()
    web: WebSettings = WebSettings()


_yaml_data = _load_yaml()


def load_settings() -> Settings:
    return Settings(**_yaml_data)


settings = load_settings()