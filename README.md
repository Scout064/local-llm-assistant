# Local LLM Assistant

A local AI assistant with voice input, ComfyUI image generation, and homelab integration — all running on-premises with a plugin architecture.

## Features

- **Local LLM** via Ollama (`qwen2.5:14b` default, tool-use capable)
- **Plugin system** — every service integration is a self-contained directory; add new ones with zero core code changes
- **Voice pipeline** — wake-word detection (openwakeword), STT (faster-whisper), VAD (silero-vad), TTS (Kokoro)
- **Web UI** — industrial/terminal theme, WebSocket streaming, conversation history
- **ComfyUI image generation** — API-format workflow patching, LoRA support, multi-workflow
- **Homelab control** — Home Assistant, Proxmox VE, Google Drive
- **SQLite persistence** — all conversations stored locally via aiosqlite
- **Optional API key auth** — shared-secret header on HTTP routes + WebSocket query param

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- [Ollama](https://ollama.com) running on your network
- ComfyUI running on your network (for image generation)
- CUDA drivers (if using GPU in the VM)
- PortAudio development headers (Linux: `sudo apt install libportaudio2`)

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
   Set `ASSISTANT_API_KEY` to a shared secret to enable HTTP/WebSocket auth. Leave empty to disable auth (use only on a trusted local network).

5. **Edit `config/settings.yaml`** — set `llm.host`, `plugins.comfyui.host`, etc. All service-specific config lives under the `plugins:` section.

6. **Add a ComfyUI workflow:**
   - Build your workflow in ComfyUI
   - Hamburger menu → "Save (API Format)"
   - Save the JSON to `plugins/builtin/comfyui/workflows/`
   - Run: `python scripts/inspect_workflow.py plugins/builtin/comfyui/workflows/default_txt2img.json`
   - Update `plugins.comfyui.node_map` in settings with the node IDs (strings, not integers)

7. **Add LoRA models** (optional):
   - Place `.safetensors` files in ComfyUI's `models/loras/` on the ComfyUI host
   - Add entries to the `plugins.comfyui.loras` list in settings

## Running

```bash
uv run python -m src.main
```

Open `http://localhost:7860` in your browser. If `api_key` is set, include it as the `X-API-Key` header for HTTP requests or as the `?key=` query parameter for WebSocket connections.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI |
| GET | `/conversations` | List conversations |
| POST | `/conversations` | Create conversation |
| PUT | `/conversations/{id}/title` | Rename conversation |
| DELETE | `/conversations/{id}` | Soft-delete conversation |
| GET | `/conversations/{id}/messages` | Get message history |
| GET | `/plugins` | List loaded plugins with status |
| WS | `/ws/{conversation_id}` | WebSocket for streaming chat |
| GET | `/output/images/{filename}` | Serve generated images |

## Architecture

```
src/
├── config.py              Settings (Pydantic BaseModel + YAML + env vars)
├── main.py                FastAPI app, lifespan, plugin/wake-word orchestration
├── plugins/               Plugin framework core (not the plugins themselves)
│   ├── base.py            Plugin ABC + ToolDefinition dataclass
│   ├── loader.py          Dynamic discovery + import
│   └── registry.py        PluginRegistry: load, health-check, tool export
├── llm/
│   ├── client.py          Ollama async wrapper (streaming + tool calls)
│   ├── agent.py           Agentic loop (stream → tool → inject → continue)
│   └── tools.py           Thin shim to PluginRegistry
├── persistence/
│   ├── db.py              aiosqlite connection + schema migration
│   └── conversations.py   CRUD for conversations and messages
├── voice/
│   ├── wakeword.py        openwakeword background listener
│   ├── vad.py             silero-vad recording with silence detection
│   ├── stt.py             faster-whisper transcription
│   └── tts.py             Kokoro/edge-tts synthesis + playback
└── web/
    ├── routes.py          FastAPI router + WebSocket handler
    └── static/            Vanilla JS frontend (industrial/terminal theme)

plugins/
├── builtin/               Ships with the project
│   ├── comfyui/           Image generation (plugin.py, service.py, tools.py)
│   ├── homeassistant/     Entity control (plugin.py, service.py)
│   ├── proxmox/           VM management (plugin.py, service.py)
│   └── google_drive/      File operations (plugin.py, service.py)
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
    config_key   = "my_service"    # reads settings.plugins.my_service

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
2. `setup(config)` — async; receives a plain dict from `settings.plugins.<config_key>`
3. `health_check()` — async; returns `True` if service reachable
4. `get_tools()` — sync; returns list of `ToolDefinition`
5. `teardown()` — async; called on shutdown

### Tool Naming Convention

Tool names must be globally unique. Use `{plugin_name}_{action}` (e.g. `comfyui_generate_image`, `homeassistant_call_service`).

## Built-in Plugins

| Plugin | Config Key | Tools | Description |
|--------|-----------|-------|-------------|
| ComfyUI | `comfyui` | `comfyui_generate_image` | Image generation with workflow patching and LoRA |
| Home Assistant | `homeassistant` | `homeassistant_call_service` | Entity state and service calls |
| Proxmox | `proxmox` | `proxmox_vm_action` | VM/CT list, start, stop, status |
| Google Drive | `google_drive` | `google_drive_list_files`, `google_drive_upload_file` | List, upload, download files |

## Configuring Wake Word

Built-in models: `hey_jarvis`, `alexa`, `hey_mycroft`, `hey_rhasspy`

To use a custom wake phrase:
1. Train a model with [openwakeword](https://github.com/davidburbery/openwakeword) (see `wake_words/README.md`)
2. Place the `.onnx` file in `wake_words/`
3. Set `voice.wake_word.model` to the file path (e.g. `wake_words/my_phrase.onnx`)

To disable: set `voice.wake_word.enabled: false` for keyboard-only mode.

## Multiple ComfyUI Workflows

```yaml
plugins:
  comfyui:
    workflows:
      default: "plugins/builtin/comfyui/workflows/default_txt2img.json"
      portrait: "plugins/builtin/comfyui/workflows/portrait_xl.json"
```

The `comfyui_generate_image` tool accepts `workflow_name` to select one.

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

- **API key auth** is optional. Set `ASSISTANT_API_KEY` in `.env` to require it on all HTTP routes (`X-API-Key` header) and WebSocket connections (`?key=` query param). Leave empty only on trusted isolated networks.
- **Path traversal protection** on `/output/images/` — resolved paths are validated against the output directory.
- **Plugin code execution** — `plugins/community/` is a privileged directory. Only add plugins you trust; loader executes arbitrary `plugin.py` files.

## Testing

```bash
uv run pytest tests/ -v
```

Tests cover: plugin loader discovery, ComfyUI `patch_workflow` logic (with and without LoRA), LoRA alias resolution, persistence CRUD, history trimming, and STT imports.

## Troubleshooting

- **Ollama unreachable:** Check `llm.host` in settings; run `ollama serve`. If the model is missing, the log will show `ollama pull <model>`.
- **ComfyUI unreachable:** Check `plugins.comfyui.host`; ensure ComfyUI is running. Plugins enter "unhealthy" state if unreachable (tools disabled, not crashed).
- **No audio device:** Install PortAudio; set `voice.input_device`/`voice.output_device` in settings.
- **CUDA OOM:** Reduce `stt_model` to `medium`; reduce image dimensions.
- **Wake word not triggering:** Lower `voice.wake_word.threshold`; verify mic works.
- **LoRA not loading:** Verify filename matches what's in ComfyUI's `models/loras/` directory on the ComfyUI host.
- **Plugin failed to load:** Check logs; ensure config key in settings matches plugin's `config_key`. Setup errors are logged and skipped — the application still starts.
- **Missing env vars:** The log will warn `env_var_not_set` if a `${VAR}` in settings.yaml has no corresponding environment variable.

## License

MIT