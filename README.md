# Local LLM Assistant

A local AI assistant with voice input, ComfyUI image generation, and homelab integration — all running on-premises with a plugin architecture.

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

5. **Edit `config/settings.yaml`** — set `llm.host`, `plugins.comfyui.host`, etc.

6. **Add a ComfyUI workflow:**
   - Build your workflow in ComfyUI
   - Hamburger menu → "Save (API Format)"
   - Save the JSON to `plugins/builtin/comfyui/workflows/`
   - Run: `python scripts/inspect_workflow.py plugins/builtin/comfyui/workflows/default_txt2img.json`
   - Update `plugins.comfyui.node_map` in settings with the node IDs

7. **Add LoRA models** (optional):
   - Place `.safetensors` files in ComfyUI's `models/loras/` on the ComfyUI host
   - Add entries to the `plugins.comfyui.loras` list in settings

## Running

```bash
uv run python -m src.main
```

Open `http://localhost:7860` in your browser.

## Systemd Service

```bash
mkdir -p ~/.config/systemd/user/
cp assistant.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now assistant
journalctl --user -fu assistant
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
        return [ToolDefinition(schema={...}, handler=self._my_action)]

    async def _my_action(self, **kwargs) -> str:
        return "result"

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

## Built-in Plugins

| Plugin | Config Key | Description |
|--------|-----------|-------------|
| ComfyUI | `comfyui` | Image generation with workflow patching and LoRA |
| Home Assistant | `homeassistant` | Entity state and service calls |
| Proxmox | `proxmox` | VM/CT list, start, stop, status |
| Google Drive | `google_drive` | List, upload, download files |

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

## Google Drive First-Run Auth (Headless VM)

Run once with X forwarding or port forwarding:
```bash
uv run python -c "from plugins.builtin.google_drive.service import GoogleDriveService; import asyncio; s = GoogleDriveService(...); s._get_service()"
```

Or copy the token file from a machine with a browser.

## Troubleshooting

- **Ollama unreachable:** Check `llm.host` in settings; run `ollama serve`
- **ComfyUI unreachable:** Check `plugins.comfyui.host`; ensure ComfyUI is running
- **No audio device:** Install PortAudio; set `voice.input_device`/`voice.output_device`
- **CUDA OOM:** Reduce `stt_model` to `medium`; reduce image dimensions
- **Wake word not triggering:** Lower `voice.wake_word.threshold`; verify mic works
- **LoRA not loading:** Verify filename matches what's in ComfyUI's `models/loras/`
- **Plugin failed to load:** Check logs; ensure config key in settings matches plugin's `config_key`

## License

MIT