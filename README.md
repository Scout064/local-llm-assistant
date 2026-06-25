# Local LLM Assistant

A local AI assistant with voice input, ComfyUI image generation, and homelab integration — all running on-premises with a plugin architecture.

## Features

- **Local LLM** via Ollama (`qwen2.5:14b` default, tool-use capable, temperature/context configurable)
- **Plugin system** — every service integration is a self-contained directory; add new ones with zero core code changes
- **Voice pipeline** — wake-word detection (openwakeword), STT (faster-whisper), VAD (silero-vad), TTS (Kokoro/edge-tts with pydub MP3 decoding)
- **Web UI** — industrial/terminal theme, WebSocket streaming, conversation history, TTS playback
- **ComfyUI image generation** — API-format workflow patching, LoRA support (strength=0 when "none"), multi-workflow
- **Homelab control** — Home Assistant (input-validated), Proxmox VE, Google Drive (query-escaped)
- **SQLite persistence** — foreign-key enforced, all conversations stored locally via aiosqlite
- **Optional API key auth** — shared-secret header on all HTTP routes + WebSocket query param (including image serving)
- **Concurrency safety** — per-conversation locks prevent interleaved writes; DB init is lock-protected; WebSocket broadcasts are snapshot-iterated
- **Security hardening** — path traversal protection, HA URL injection prevention, Drive query escaping, XSS-safe DOM creation

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- [Ollama](https://ollama.com) running on your network
- ComfyUI running on your network (for image generation)
- CUDA drivers (if using GPU in the VM)
- PortAudio development headers (Linux: `sudo apt install libportaudio2`)
- ffmpeg (for edge-tts MP3 decoding via pydub; Linux: `sudo apt install ffmpeg`)

## Setup

1. **Install Ollama model:**
   ```bash
   ollama pull qwen2.5:14b
   ```

2. **Install Python dependencies:**
   ```bash
   uv sync
   ```

3. **GPU Setup** (if CUDA is available):
   ```bash
   uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 --force-reinstall
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your tokens and API keys
   ```
   Set `ASSISTANT_API_KEY` to a shared secret to enable HTTP/WebSocket auth. Leave empty to disable auth (use only on a trusted local network). Environment variables are loaded automatically from `.env` via `python-dotenv`.

5. **Edit `config/settings.yaml`** — set `llm.host`, `plugins.comfyui.host`, etc. All service-specific config lives under the `plugins:` section. The `temperature` and `context_window` settings are now passed to Ollama.

6. **Add a ComfyUI workflow:**
   - Build your workflow in ComfyUI
   - Hamburger menu → "Save (API Format)"
   - Save the JSON to `plugins/builtin/comfyui/workflows/`
   - Run: `python scripts/inspect_workflow.py plugins/builtin/comfyui/workflows/default_txt2img.json`
   - Update `plugins.comfyui.node_map` in settings with the node IDs (strings, not integers)

7. **Add LoRA models** (optional):
   - Place `.safetensors` files in ComfyUI's `models/loras/` on the ComfyUI host
   - Add entries to the `plugins.comfyui.loras` list in settings
   - When LoRA alias "none" is selected, strength is automatically set to 0.0

## Running

```bash
uv run python -m src.main
```

Open `http://localhost:7860` in your browser. If `api_key` is set, include it as the `X-API-Key` header for HTTP requests or as the `?key=` query parameter for WebSocket connections and image URLs.

## Voice Pipeline

The voice pipeline is fully wired:

1. **Wake-word detection** (openwakeword) runs in a background thread with cooldown to prevent re-triggers
2. **VAD** (silero-vad) records until silence detected
3. **STT** (faster-whisper) transcribes the audio
4. **Transcription** is broadcast to WebSocket clients and queued for TTS
5. **TTS** (Kokoro or edge-tts) synthesizes and plays audio through speakers

The TTS playback thread starts lazily on first synthesis request (not at import time). Sentence splitting uses a regex that avoids breaking on abbreviations and decimals.

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | No | Web UI |
| GET | `/static/*` | No | Static assets |
| GET | `/conversations` | Yes | List conversations |
| POST | `/conversations` | Yes | Create conversation |
| PUT | `/conversations/{id}/title` | Yes | Rename conversation (256-char cap) |
| DELETE | `/conversations/{id}` | Yes | Soft-delete conversation |
| GET | `/conversations/{id}/messages` | Yes | Get message history |
| GET | `/plugins` | Yes | List loaded plugins with status |
| WS | `/ws/{conversation_id}` | Yes* | WebSocket for streaming chat |
| GET | `/output/images/{filename}` | Yes | Serve generated images (traversal-protected) |

*WebSocket validates conversation exists before accepting. Auth via `?key=` query param.

## Architecture

```
src/
├── config.py              Settings (Pydantic BaseModel + YAML + env vars + dotenv)
├── main.py                FastAPI app, lifespan, plugin/wake-word/TTS orchestration
├── plugins/               Plugin framework core (not the plugins themselves)
│   ├── base.py            Plugin ABC + ToolDefinition dataclass
│   ├── loader.py          Dynamic discovery + import (full-path module names)
│   └── registry.py        PluginRegistry: load, health-check, tool export (cached)
├── llm/
│   ├── client.py          Ollama async wrapper (streaming + tool calls + temperature)
│   ├── agent.py           Agentic loop (multi-tool per turn, malformed JSON safe)
│   └── tools.py           Thin shim to PluginRegistry
├── persistence/
│   ├── db.py              aiosqlite (FK-enforced, lock-protected init)
│   └── conversations.py   CRUD with title length cap
├── voice/
│   ├── wakeword.py        openwakeword listener with cooldown
│   ├── vad.py             silero-vad recording with silence detection
│   ├── stt.py             faster-whisper transcription
│   └── tts.py             Kokoro/edge-tts (pydub MP3, lazy thread, regex sentences)
└── web/
    ├── routes.py          FastAPI router (per-conv lock, auth on all routes)
    └── static/            Vanilla JS frontend (XSS-safe DOM, industrial theme)

plugins/
├── builtin/               Ships with the project
│   ├── comfyui/           Image generation (LoRA strength=0 for "none")
│   ├── homeassistant/     Entity control (URL injection-validated)
│   ├── proxmox/           VM management (specific exception handling)
│   └── google_drive/      File operations (query-escaped)
└── community/             User-added plugins (gitignored)
```

## How to Write a Plugin

A plugin is a directory in `plugins/builtin/` or `plugins/community/` containing at minimum `plugin.py` and `__init__.py`.

```python
# plugins/community/my_service/plugin.py
from src.plugins.base import Plugin, ToolDefinition


class MyServicePlugin(Plugin):
    name         = "my_service"
    display_name = "My Service"
    version      = "0.1.0"
    description  = "Does something useful."
    config_key   = "my_service"

    async def setup(self, config: dict) -> None:
        self.host = config["host"]
        self.api_key = config.get("api_key", "")

    async def health_check(self) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.host}/health", timeout=3.0)
                return resp.status_code == 200
        except Exception:
            return False

    def get_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition(
            schema={
                "type": "function",
                "function": {
                    "name": "my_service_action",
                    "description": "Does something with My Service.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "What to do"}
                        },
                        "required": ["query"]
                    }
                }
            },
            handler=self._my_action,
        )]

    async def _my_action(self, query: str) -> str:
        return f"Done: {query}"

    async def teardown(self) -> None:
        pass


PLUGIN_CLASS = MyServicePlugin
```

Then add to `config/settings.yaml`:
```yaml
plugins:
  my_service:
    host: "http://my-service.local:9000"
    api_key: "${MY_SERVICE_API_KEY}"
```

**No changes to any core file are needed.** Just drop the directory and add config.

### Plugin Lifecycle

1. `__init__()` — synchronous, no I/O
2. `setup(config)` — async; receives a plain dict from `settings.plugins.<config_key>` (Pydantic model is converted via `model_dump()`)
3. `health_check()` — async; returns `True` if service reachable
4. `get_tools()` — sync; returns list of `ToolDefinition`
5. `teardown()` — async; called on shutdown

### Tool Naming Convention

Tool names must be globally unique (enforced by registry with dedup). Use `{plugin_name}_{action}`.

## Built-in Plugins

| Plugin | Config Key | Tools | Description |
|--------|-----------|-------|-------------|
| ComfyUI | `comfyui` | `comfyui_generate_image` | Image generation with workflow patching and LoRA |
| Home Assistant | `homeassistant` | `homeassistant_call_service` | Entity control (input-validated) |
| Proxmox | `proxmox` | `proxmox_vm_action` | VM/CT list, start, stop, status |
| Google Drive | `google_drive` | `google_drive_list_files`, `google_drive_upload_file` | List, upload, download files |

## Configuring Wake Word

Built-in models: `hey_jarvis`, `alexa`, `hey_mycroft`, `hey_rhasspy`

To use a custom wake phrase:
1. Train a model with [openwakeword](https://github.com/davidburbery/openwakeword) (see `wake_words/README.md`)
2. Place the `.onnx` file in `wake_words/`
3. Set `voice.wake_word.model` to the file path (e.g. `wake_words/my_phrase.onnx`)

To disable: set `voice.wake_word.enabled: false` for keyboard-only mode. A cooldown period prevents re-triggers during recording.

## Multiple ComfyUI Workflows

```yaml
plugins:
  comfyui:
    workflows:
      default: "plugins/builtin/comfyui/workflows/default_txt2img.json"
      portrait: "plugins/builtin/comfyui/workflows/portrait_xl.json"
```

The `comfyui_generate_image` tool accepts `workflow_name` to select one. Both `width` and `height` are correctly patched (no silent drops).

## Systemd Service

```bash
mkdir -p ~/.config/systemd/user/
cp assistant.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now assistant
journalctl --user -fu assistant
```

## Google Drive First-Run Auth (Headless VM)

Run once with X forwarding or port forwarding from a machine with a browser:
```bash
uv run python -c "from plugins.builtin.google_drive.service import GoogleDriveService; s = GoogleDriveService('~/.config/assistant/gdrive_credentials.json', '~/.config/assistant/gdrive_token.json'); s._get_service()"
```

Or copy `~/.config/assistant/gdrive_token.json` from a machine that has already authenticated.

## Security Notes

- **API key auth** is optional. Set `ASSISTANT_API_KEY` in `.env` to require it on all HTTP routes (`X-API-Key` header or `?key=` query param) and WebSocket connections. Leave empty only on trusted isolated networks.
- **Path traversal protection** on `/output/images/` — resolved paths are validated against the output directory via `relative_to()`.
- **Home Assistant input validation** — `entity_id`, `domain`, `service` are regex-validated before URL interpolation.
- **Google Drive query escaping** — search queries have single quotes escaped to prevent `q` clause injection.
- **SQLite foreign keys** — enabled on every connection; orphan messages are rejected.
- **Per-conversation locking** — concurrent WebSocket messages on the same conversation are serialized to prevent history corruption.
- **XSS-safe frontend** — image elements are created via `createElement`, not `innerHTML`.
- **Plugin code execution** — `plugins/community/` is a privileged directory. Only add plugins you trust; loader executes arbitrary `plugin.py` files.

## Testing

```bash
uv run pytest tests/ -v
```

Tests cover:
- Plugin loader discovery, setup, tool registration, and health-check-failure graceful skip
- Registry duplicate tool name dedup (cross-plugin)
- ComfyUI `patch_workflow` logic (with and without LoRA, width+height, seed generation)
- LoRA alias resolution from settings
- Persistence CRUD, message ordering, soft-delete, foreign-key enforcement, title length cap
- History trimming logic
- STT module imports and WAV transcription (skips if torch unavailable)

## Troubleshooting

- **Ollama unreachable:** Check `llm.host` in settings; run `ollama serve`. If the model is missing, the log will show `ollama pull <model>`. The model check requires an exact match (no variant fallback).
- **ComfyUI unreachable:** Check `plugins.comfyui.host`; ensure ComfyUI is running. Plugins enter "unhealthy" state if unreachable (tools disabled, not crashed).
- **No audio device:** Install PortAudio; set `voice.input_device`/`voice.output_device` in settings.
- **CUDA OOM:** Reduce `stt_model` to `medium`; reduce image dimensions.
- **Wake word not triggering:** Lower `voice.wake_word.threshold`; verify mic works. A cooldown prevents re-triggers during recording.
- **LoRA not loading:** Verify filename matches what's in ComfyUI's `models/loras/` directory on the ComfyUI host. When alias "none" is selected, strength is set to 0.0.
- **Plugin failed to load:** Check logs; ensure config key in settings matches plugin's `config_key`. Setup errors are logged and skipped — the application still starts.
- **Missing env vars:** The log will warn `env_var_not_set` if a `${VAR}` in settings.yaml has no corresponding environment variable. `.env` is loaded automatically via `python-dotenv`.
- **edge-tts fails:** Ensure `ffmpeg` is installed (pydub requires it for MP3 decoding). Kokoro is the recommended backend.

## License

MIT