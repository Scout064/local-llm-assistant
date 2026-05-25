# AGENTS.md — Local LLM Assistant with ComfyUI & Homelab Integration

> Instruction file for opencode. Read this entire file before writing any code.
> When in doubt, re-read the relevant section rather than making assumptions.

---

## 1. Project Overview

Build a local AI assistant that:

- Accepts input via **voice** (configurable wake-word → microphone → STT) or **keyboard** (web UI chat)
- Runs inference through a **locally hosted LLM via Ollama**
- Can autonomously call **tools** registered by plugins when contextually appropriate or explicitly instructed
- Responds via **text** (web UI) and **synthesised speech** (TTS → speakers)
- Persists **all conversations to a local SQLite database**
- Exposes a **plugin system**: every external service integration (ComfyUI, Home Assistant, Proxmox, Google Drive, or anything else) is a self-contained plugin that can be added by dropping a directory into `plugins/` with zero changes to core code

The system runs inside a **Proxmox VM** (Linux, no Docker). All components run as native Python processes. ComfyUI and Ollama run on the Proxmox host or another VM and are accessed over the local network.

---

## 2. Architecture Decisions (fixed — do not re-litigate)

| Concern | Choice | Rationale |
|---|---|---|
| LLM serving | **Ollama** | Native tool-use, simple REST API, model management built in |
| Default model | **`qwen2.5:14b`** (Q4_K_M) | Best tool-use at this size; ~9 GB VRAM. Fallback: `llama3.1:8b` |
| **Service integrations** | **Plugin system** — every service is a plugin | Zero-touch extensibility; no core edits to add a service |
| Wake-word | **`openwakeword`** | Fully local, no API key, ONNX-based, configurable phrase |
| STT | **`faster-whisper`** | Fastest local Whisper; GPU or CPU |
| TTS | **Kokoro** (ONNX) | High quality, fully local. Fallback: `edge-tts` |
| VAD | **`silero-vad`** | Small, accurate, 30ms chunk processing |
| Web backend | **FastAPI** + **Uvicorn** | Async-native; WebSocket for streaming and audio events |
| Web frontend | **Vanilla JS + WebSocket** | Zero build step; served statically |
| Audio I/O | **`sounddevice`** | Works with PulseAudio/PipeWire on Linux |
| Persistence | **SQLite** via **`aiosqlite`** | Zero-server, file-based, async |
| Config | **`config/settings.yaml`** + `.env` | Single source of truth; env vars override yaml |
| Packaging | **`pyproject.toml`** + **`uv`** | Modern, fast, reproducible |
| Deployment | **Systemd user service** | Runs as a VM service; `uv run` in unit file |

---

## 3. Repository Structure

```
assistant/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── assistant.service              ← systemd unit file template
│
├── config/
│   └── settings.yaml              ← core config + per-plugin config sections
│
├── data/
│   └── conversations.db           ← SQLite; created at first run; gitignored
│
├── output/
│   └── images/                    ← generated images; gitignored
│
├── wake_words/
│   └── README.md                  ← instructions for custom .onnx wake-word models
│
│   # ── Plugin directories ──────────────────────────────────────────────────
│   # Built-in plugins ship with the project. Community plugins are user-added.
│   # Both are discovered and loaded identically — the split is organisational only.
│
├── plugins/
│   ├── README.md                  ← how to write a plugin (mirrors §11 of this file)
│   │
│   ├── builtin/                   ← ships with the project; do not remove
│   │   ├── comfyui/
│   │   │   ├── __init__.py
│   │   │   ├── plugin.py          ← exports PLUGIN instance
│   │   │   ├── service.py         ← ComfyUI HTTP client
│   │   │   ├── tools.py           ← generate_image tool definition + handler
│   │   │   └── workflows/         ← user-supplied API-format workflow JSONs
│   │   │       └── README.md
│   │   ├── homeassistant/
│   │   │   ├── __init__.py
│   │   │   ├── plugin.py
│   │   │   └── service.py
│   │   ├── proxmox/
│   │   │   ├── __init__.py
│   │   │   ├── plugin.py
│   │   │   └── service.py
│   │   └── google_drive/
│   │       ├── __init__.py
│   │       ├── plugin.py
│   │       └── service.py
│   │
│   └── community/                 ← user-added plugins; gitignored except README
│       └── README.md
│   # ─────────────────────────────────────────────────────────────────────────
│
├── scripts/
│   └── inspect_workflow.py        ← prints ComfyUI workflow node IDs
│
├── src/
│   ├── __init__.py
│   ├── main.py                    ← FastAPI app, lifespan, startup orchestration
│   ├── config.py                  ← settings singleton
│   │
│   ├── plugins/                   ← plugin system core (not the plugins themselves)
│   │   ├── __init__.py
│   │   ├── base.py                ← Plugin base class, ToolDefinition dataclass
│   │   ├── registry.py            ← PluginRegistry: load, health-check, tool export
│   │   └── loader.py              ← dynamic import + discovery logic
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── tools.py               ← thin shim: pulls all tools from PluginRegistry
│   │   └── agent.py
│   │
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── wakeword.py
│   │   ├── vad.py
│   │   ├── stt.py
│   │   └── tts.py
│   │
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   └── conversations.py
│   │
│   └── web/
│       ├── __init__.py
│       ├── routes.py
│       └── static/
│           ├── index.html
│           ├── app.js
│           └── style.css
│
└── tests/
    ├── test_plugin_loader.py
    ├── test_comfyui_plugin.py
    ├── test_stt.py
    └── test_persistence.py
```

---

## 4. Dependencies

```toml
[project]
name = "local-assistant"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "ollama>=0.3.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "websockets>=13.0",
    "aiohttp>=3.10.0",
    "aiofiles>=23.0.0",
    "openwakeword>=0.6.0",
    "faster-whisper>=1.0.3",
    "kokoro>=0.9.2",
    "soundfile>=0.12.1",
    "edge-tts>=6.1.12",
    "torch>=2.3.0",
    "torchaudio>=2.3.0",
    "sounddevice>=0.4.7",
    "numpy>=1.26.0",
    "aiosqlite>=0.20.0",
    "pyyaml>=6.0.1",
    "pydantic>=2.8.0",
    "pydantic-settings>=2.4.0",
    "python-dotenv>=1.0.0",
    "google-api-python-client>=2.140.0",
    "google-auth-httplib2>=0.2.0",
    "google-auth-oauthlib>=1.2.0",
    "proxmoxer>=2.0.0",
    "pillow>=10.4.0",
    "httpx>=0.27.0",
    "structlog>=24.0.0",
]
```

After `uv sync`, if CUDA is available on the VM:
```bash
uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 --force-reinstall
```

---

## 5. Implementation Phases

Execute in order. Each phase must be complete and testable before starting the next.

### Phase 1 — Skeleton, Config & Persistence

1. Create `pyproject.toml`, `.env.example`, `config/settings.yaml` (see §7)
2. Implement `src/config.py` — Pydantic Settings; reads `settings.yaml`; substitutes `${ENV_VAR}` tokens; exposes `settings` singleton
3. Implement `src/persistence/db.py` — aiosqlite connection; schema migration on startup (see §8 for schema)
4. Implement `src/persistence/conversations.py` — CRUD layer (see §8)
5. Implement `src/main.py` — FastAPI app with lifespan context manager; DB init; no routes yet; confirm it starts
6. Write `README.md` skeleton

### Phase 2 — Plugin System Core

This is the foundation all services build on. Implement it fully before any plugin.

1. Implement `src/plugins/base.py` (see §9 — Plugin Base Class)
2. Implement `src/plugins/loader.py` (see §9 — Plugin Discovery)
3. Implement `src/plugins/registry.py` (see §9 — Plugin Registry)
4. Wire `PluginRegistry` into `main.py` lifespan: discover → load → health-check → register tools
5. Implement `src/llm/tools.py` as a thin shim that calls `registry.get_all_tools()` — no tool definitions live here
6. Write `tests/test_plugin_loader.py` — test discovery with a minimal stub plugin

### Phase 3 — LLM Agent Core

1. Implement `src/llm/client.py` — async Ollama wrapper; `chat(messages, tools) -> AsyncIterator[str | ToolCall]`
2. Implement `src/llm/agent.py` — agentic loop (see §10)

### Phase 4 — Built-in Plugins

Implement each plugin in `plugins/builtin/`. Each must conform to the Plugin interface from §9.

**Order:**
1. `comfyui/` — image generation (see §12 for ComfyUI specifics and LoRA)
2. `homeassistant/` — entity state + service calls
3. `proxmox/` — VM/CT list, start, stop, status
4. `google_drive/` — list, upload, download

Each plugin gets a config section under `plugins:` in `settings.yaml` (see §7).

### Phase 5 — Web UI

Design direction: **industrial/terminal** — `#0d0d0d` background, `JetBrains Mono` (Google Fonts), amber `#f59e0b` accent. No gradients, 2px max border-radius. Left sidebar lists conversations; right panel is active chat; a narrow status strip runs at top.

1. Implement `src/web/routes.py`:
   - `GET /` → `index.html`
   - `WebSocket /ws/{conversation_id}`
   - `GET /conversations` → JSON list
   - `POST /conversations` → create, return id
   - `PUT /conversations/{id}/title`
   - `DELETE /conversations/{id}` → soft delete
   - `GET /conversations/{id}/messages`
   - `GET /output/images/{filename}`
   - `GET /plugins` → JSON list of loaded plugins with name, display_name, status, tools[] — for a status panel in the UI
2. Implement `src/web/static/` (see §13 for WebSocket protocol)

### Phase 6 — Voice Pipeline

1. `src/voice/wakeword.py` — openwakeword background listener (see §14)
2. `src/voice/vad.py` — silero-vad accumulation
3. `src/voice/stt.py` — faster-whisper transcription
4. `src/voice/tts.py` — Kokoro synthesis; sentence-buffered playback

### Phase 7 — Systemd Unit File

Write `assistant.service` (see §15). Document install in README.md.

---

## 6. Configuration Schema (`config/settings.yaml`)

```yaml
llm:
  host: "http://192.168.1.x:11434"
  model: "qwen2.5:14b"
  system_prompt: |
    You are a capable local assistant. You have tools registered by plugins for
    image generation, home automation, server management, and file access.
    Use tools when they genuinely help. Generate images when visuals enrich a response.
    Be concise. Prefer action over explanation.
  context_window: 8192
  temperature: 0.7
  max_history_messages: 40       # messages sent to Ollama per turn (full history always in DB)

voice:
  enabled: true
  input_device: null             # null = system default; or device index/name
  output_device: null

  wake_word:
    enabled: true
    # Built-in names: "hey_jarvis", "alexa", "hey_mycroft", "hey_rhasspy"
    # Custom: path to a .onnx file in wake_words/, e.g. "wake_words/my_phrase.onnx"
    model: "hey_jarvis"
    threshold: 0.5               # 0.0–1.0; higher = fewer false positives
    listen_timeout: 15.0         # seconds to keep listening after wake word

  stt_model: "large-v3"
  stt_device: "cuda:0"           # "cuda:0", "cuda:1", or "cpu"
  tts_backend: "kokoro"          # "kokoro" or "edge"
  tts_voice: "af_heart"
  vad_threshold: 0.5
  silence_ms: 800

persistence:
  db_path: "./data/conversations.db"

web:
  host: "0.0.0.0"
  port: 7860
  log_level: "info"

# ── Plugin configuration ─────────────────────────────────────────────────────
# Each plugin reads its own section from here via plugin.config_key.
# Keys under plugins: are free-form; each plugin defines what it expects.

plugins:
  # Directories to scan for plugins (in addition to the built-ins).
  # Built-in plugins at plugins/builtin/ are always loaded first.
  extra_dirs:
    - "./plugins/community"

  # Set to false to disable a specific plugin without removing it.
  disabled: []                   # e.g. ["google_drive", "proxmox"]

  comfyui:
    host: "http://192.168.1.x:8188"
    output_dir: "./output/images"
    # API-format workflow JSONs. Key = alias used in the generate_image tool.
    # Export from ComfyUI: hamburger → "Save (API Format)"
    workflows:
      default: "plugins/builtin/comfyui/workflows/default_txt2img.json"
      # flux:   "plugins/builtin/comfyui/workflows/flux_schnell.json"
    # Node IDs from your workflow JSON. Run: python scripts/inspect_workflow.py <file>
    node_map:
      positive_prompt: "6"
      negative_prompt: "7"
      sampler: "3"
      latent_image: "5"
      lora_loader: "10"          # omit this key entirely if your workflow has no LoRA node
    # LoRA files must exist in ComfyUI's models/loras/ on the ComfyUI host.
    loras:
      - alias: "none"
        filename: ""
      - alias: "detail"
        filename: "add_detail.safetensors"

  homeassistant:
    host: "http://homeassistant.local:8123"
    token: "${HA_TOKEN}"

  proxmox:
    host: "https://proxmox.local:8006"
    user: "root@pam"
    token_name: "${PROXMOX_TOKEN_NAME}"
    token_value: "${PROXMOX_TOKEN_VALUE}"
    verify_ssl: false

  google_drive:
    credentials_file: "~/.config/assistant/gdrive_credentials.json"
    token_file: "~/.config/assistant/gdrive_token.json"

  # Community plugin example — a user-added Jellyfin plugin would go here:
  # jellyfin:
  #   host: "http://jellyfin.local:8096"
  #   api_key: "${JELLYFIN_API_KEY}"
```

---

## 7. Conversation Persistence

### Schema

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'New conversation',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL,         -- 'user' | 'assistant' | 'tool'
    content         TEXT NOT NULL,
    tool_name       TEXT,
    tool_call_json  TEXT,
    image_paths     TEXT,                  -- JSON array
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, created_at);
```

### `conversations.py` API

```python
async def create_conversation(title="New conversation") -> str
async def get_conversation(conversation_id: str) -> dict | None
async def list_conversations(include_deleted=False) -> list[dict]
async def update_conversation_title(conversation_id: str, title: str)
async def soft_delete_conversation(conversation_id: str)
async def add_message(conversation_id, role, content,
                      tool_name=None, tool_call_json=None, image_paths=None) -> str
async def get_messages(conversation_id: str) -> list[dict]
```

### History Loading

At the start of each `agent.run()` call, load all messages and reconstruct the Ollama messages list. If `len(messages) > settings.llm.max_history_messages`, trim oldest non-system messages. Always persist the full history to DB — trimming only affects what is sent to the model.

### Auto-Title

After the first user message in a new conversation, call Ollama in a separate non-streamed request to generate a 4–6 word title. Update via `update_conversation_title()`. Broadcast `{type: "conversation_titled", id, title}` to the frontend.

---

## 8. Plugin System

This is the core architectural layer. Read this section fully before implementing anything in Phase 2.

### 8.1 Plugin Base Class (`src/plugins/base.py`)

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

@dataclass
class ToolDefinition:
    """A single tool the LLM can call."""
    schema: dict                                          # Ollama-compatible JSON schema
    handler: Callable[..., Awaitable[str]]                # async fn; returns string result
    # handler receives keyword args matching the tool's parameter names


class Plugin(ABC):
    """
    Base class for all assistant plugins.

    A plugin encapsulates one external service integration. It declares:
    - Its identity (name, display_name, version, description)
    - Which config key it reads from settings.yaml under plugins:
    - What tools it contributes to the LLM tool registry
    - How to verify the service is reachable (health_check)

    Lifecycle (called by PluginRegistry):
      1. __init__()         — synchronous; no I/O
      2. setup(config)      — async; read config, create HTTP clients, load models, etc.
      3. health_check()     — async; return True if service reachable
      4. get_tools()        — synchronous; return tool list (called after setup)
      5. teardown()         — async; called on shutdown
    """

    # ── Identity (override as class attributes) ───────────────────────────────

    name: str                    # snake_case unique identifier, e.g. "jellyfin"
    display_name: str            # human-readable, e.g. "Jellyfin Media Server"
    version: str = "0.1.0"
    description: str = ""
    config_key: str | None = None  # key under plugins: in settings.yaml; None = no config

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def setup(self, config: dict[str, Any]) -> None:
        """
        Called once at startup with this plugin's config dict
        (the value of settings.plugins.<config_key>, or {} if config_key is None).
        Raise an exception to abort loading this plugin.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the backing service is reachable."""
        ...

    @abstractmethod
    def get_tools(self) -> list[ToolDefinition]:
        """
        Return the list of tools this plugin contributes.
        Called after setup(). May return [] if the plugin has no tools
        (e.g. a plugin that only provides background functionality).
        """
        ...

    async def teardown(self) -> None:
        """Called on application shutdown. Close connections, etc."""
        pass
```

### 8.2 Plugin Discovery (`src/plugins/loader.py`)

```python
import importlib
import importlib.util
import inspect
from pathlib import Path
from src.plugins.base import Plugin


def discover_plugins(directories: list[Path]) -> list[type[Plugin]]:
    """
    Scan each directory for plugins. A plugin directory must contain a plugin.py
    that defines exactly one concrete subclass of Plugin or exports a module-level
    PLUGIN_CLASS: type[Plugin].

    Discovery order: directories are scanned left-to-right; within a directory,
    subdirectories are sorted alphabetically. Built-in plugins are always passed
    first by the registry so they load before community plugins.
    """
    found: list[type[Plugin]] = []

    for base_dir in directories:
        if not base_dir.is_dir():
            continue
        for plugin_dir in sorted(base_dir.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
                continue
            plugin_file = plugin_dir / "plugin.py"
            if not plugin_file.exists():
                continue
            try:
                cls = _load_plugin_class(plugin_file, plugin_dir.name)
                if cls is not None:
                    found.append(cls)
            except Exception as exc:
                # Log warning; never crash discovery because of one bad plugin
                import structlog
                structlog.get_logger().warning(
                    "plugin_load_failed", path=str(plugin_file), error=str(exc)
                )
    return found


def _load_plugin_class(plugin_file: Path, dir_name: str) -> type[Plugin] | None:
    module_name = f"plugins.{dir_name}.plugin"
    spec = importlib.util.spec_from_file_location(module_name, plugin_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Prefer explicit PLUGIN_CLASS export
    if hasattr(module, "PLUGIN_CLASS"):
        return module.PLUGIN_CLASS

    # Fall back: find the one concrete Plugin subclass defined in this module
    classes = [
        obj for _, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, Plugin) and obj is not Plugin and obj.__module__ == module_name
    ]
    if len(classes) == 1:
        return classes[0]
    if len(classes) > 1:
        raise ValueError(f"Multiple Plugin subclasses found; export PLUGIN_CLASS explicitly")
    return None
```

### 8.3 Plugin Registry (`src/plugins/registry.py`)

```python
from pathlib import Path
from src.plugins.base import Plugin, ToolDefinition
from src.plugins.loader import discover_plugins
import structlog

log = structlog.get_logger()


class PluginRegistry:
    """
    Owns the full lifecycle of all plugins.
    Instantiated once in main.py lifespan and stored as app state.
    """

    def __init__(self):
        self._plugins: list[Plugin] = []
        self._tools: list[ToolDefinition] = []
        self._failed: list[str] = []

    async def load_all(self, settings) -> None:
        """Discover, setup, health-check, and register all plugins."""
        builtin_dir = Path("plugins/builtin")
        extra_dirs  = [Path(d) for d in (settings.plugins.extra_dirs or [])]
        disabled    = set(settings.plugins.disabled or [])

        plugin_classes = discover_plugins([builtin_dir] + extra_dirs)

        for cls in plugin_classes:
            instance = cls()

            if instance.name in disabled:
                log.info("plugin_disabled", name=instance.name)
                continue

            plugin_config = {}
            if instance.config_key:
                plugin_config = getattr(settings.plugins, instance.config_key, {}) or {}

            try:
                await instance.setup(plugin_config)
            except Exception as exc:
                log.warning("plugin_setup_failed", name=instance.name, error=str(exc))
                self._failed.append(instance.name)
                continue

            healthy = False
            try:
                healthy = await instance.health_check()
            except Exception as exc:
                log.warning("plugin_health_check_error", name=instance.name, error=str(exc))

            if not healthy:
                log.warning("plugin_unhealthy", name=instance.name,
                            message="Plugin loaded but service unreachable; tools disabled")
                # Still register the plugin so it shows in /plugins status endpoint
                self._plugins.append(instance)
                self._failed.append(instance.name)
                continue

            self._plugins.append(instance)
            tools = instance.get_tools()
            self._tools.extend(tools)
            log.info("plugin_loaded", name=instance.name,
                     tools=[t.schema["function"]["name"] for t in tools])

    async def teardown_all(self) -> None:
        for plugin in self._plugins:
            try:
                await plugin.teardown()
            except Exception as exc:
                log.warning("plugin_teardown_error", name=plugin.name, error=str(exc))

    def get_all_tools(self) -> list[ToolDefinition]:
        return list(self._tools)

    def get_ollama_tool_schemas(self) -> list[dict]:
        return [t.schema for t in self._tools]

    def get_tool_handler(self, tool_name: str) -> ...:
        for tool in self._tools:
            if tool.schema["function"]["name"] == tool_name:
                return tool.handler
        return None

    def get_status(self) -> list[dict]:
        """For the /plugins web endpoint."""
        failed = set(self._failed)
        return [
            {
                "name": p.name,
                "display_name": p.display_name,
                "version": p.version,
                "description": p.description,
                "status": "unhealthy" if p.name in failed else "ok",
                "tools": [
                    t.schema["function"]["name"]
                    for t in self._tools
                    if t in p.get_tools()   # only tools from this plugin
                ],
            }
            for p in self._plugins
        ]
```

### 8.4 Wiring in `main.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.plugins.registry import PluginRegistry
from src.persistence.db import init_db
from src.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    registry = PluginRegistry()
    await registry.load_all(settings)
    app.state.registry = registry
    yield
    await registry.teardown_all()

app = FastAPI(lifespan=lifespan)
```

In `src/llm/tools.py`, pull the registry from app state — do not import it directly. Pass it into the agent constructor so the agent always calls `registry.get_ollama_tool_schemas()` and `registry.get_tool_handler(name)` at runtime.

### 8.5 Writing a Plugin (contract for plugin authors)

A plugin is a directory containing at least `plugin.py` and `__init__.py`. It may have as many additional files as needed.

**Minimal template:**

```python
# plugins/community/my_service/plugin.py
from src.plugins.base import Plugin, ToolDefinition


class MyServicePlugin(Plugin):
    name        = "my_service"
    display_name = "My Service"
    version     = "0.1.0"
    description = "Does something useful."
    config_key  = "my_service"    # reads settings.plugins.my_service

    async def setup(self, config: dict) -> None:
        self.host = config["host"]
        self.api_key = config.get("api_key", "")
        # initialise HTTP client, etc.

    async def health_check(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.host}/health", timeout=aiohttp.ClientTimeout(total=3)) as r:
                    return r.status == 200
        except Exception:
            return False

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
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
                handler=self._handle_action
            )
        ]

    async def _handle_action(self, query: str) -> str:
        # call the service; return a string result for the LLM
        return f"Done: {query}"

    async def teardown(self) -> None:
        pass  # close connections


PLUGIN_CLASS = MyServicePlugin
```

**Then add to `config/settings.yaml`:**
```yaml
plugins:
  my_service:
    host: "http://my-service.local:9000"
    api_key: "${MY_SERVICE_API_KEY}"
```

**That is the complete process.** No changes to any core file.

---

## 9. LLM Agent Loop (`src/llm/agent.py`)

```python
async def run(conversation_id: str, user_message: str,
              registry: PluginRegistry) -> AsyncIterator[str | AgentEvent]:

    # 1. Persist user message
    await add_message(conversation_id, "user", user_message)

    # 2. Load history from DB; trim if needed
    messages = await _build_messages(conversation_id)

    # 3. Agentic loop
    response_text = ""
    while True:
        text_chunks = []
        tool_call = None

        async for item in client.chat(messages, registry.get_ollama_tool_schemas()):
            if isinstance(item, str):
                text_chunks.append(item)
                yield item                        # stream to WebSocket immediately
            elif isinstance(item, ToolCall):
                tool_call = item
                break                             # process tool, then continue loop

        if text_chunks:
            response_text = "".join(text_chunks)
            # Persist only when we have a complete text segment
            await add_message(conversation_id, "assistant", response_text)

        if tool_call is None:
            break                                 # model is done

        # Execute tool
        yield AgentEvent("tool_start", tool=tool_call.name)
        handler = registry.get_tool_handler(tool_call.name)
        if handler is None:
            result = f"Error: tool '{tool_call.name}' not found"
        else:
            try:
                result = await handler(**tool_call.args)
            except Exception as exc:
                result = f"Error: {exc}"

        yield AgentEvent("tool_done", tool=tool_call.name, result=result)

        # Inject result and continue
        await add_message(conversation_id, "tool", str(result), tool_name=tool_call.name)
        messages.append({"role": "tool", "content": str(result), "name": tool_call.name})
```

---

## 10. ComfyUI Plugin Detail (`plugins/builtin/comfyui/`)

### Workflow approach

The user is correct: export a workflow from ComfyUI in **API format** (hamburger → "Save (API Format)"), drop the JSON into `plugins/builtin/comfyui/workflows/`, reference it in `settings.yaml`. No other steps.

Run `python scripts/inspect_workflow.py <file>` to print all node IDs and class types, then fill in `node_map` in settings.

### LoRA support

The `generate_image` tool accepts `lora_alias` and `lora_strength`. The plugin resolves the alias to a filename via `settings.plugins.comfyui.loras` and patches the LoRA loader node. If `node_map` has no `lora_loader` key, LoRA patching is silently skipped — LoRA-free workflows work without config changes.

### Workflow patching

```python
def patch_workflow(workflow: dict, node_map: dict, params: dict) -> dict:
    import copy
    wf = copy.deepcopy(workflow)
    fields = {
        "positive_prompt": (["text"],          params.get("prompt")),
        "negative_prompt": (["text"],          params.get("negative_prompt")),
        "sampler":         (["steps"],         params.get("steps")),
        "sampler":         (["cfg"],           params.get("cfg")),
        "sampler":         (["seed"],          params.get("seed")),
        "latent_image":    (["width"],         params.get("width")),
        "latent_image":    (["height"],        params.get("height")),
    }
    for map_key, (input_keys, value) in fields.items():
        if map_key in node_map and value is not None:
            node = wf[node_map[map_key]]["inputs"]
            for k in input_keys:
                node[k] = value

    if "lora_loader" in node_map:
        lora_filename = params.get("lora_filename", "")
        default_strength = 1.0 if lora_filename else 0.0
        lora_node = wf[node_map["lora_loader"]]["inputs"]
        lora_node["lora_name"]       = lora_filename
        lora_node["strength_model"]  = params.get("lora_strength", default_strength)
        lora_node["strength_clip"]   = params.get("lora_strength", default_strength)

    return wf
```

### ComfyUI HTTP API

```
POST {host}/prompt
  Body: {"prompt": <workflow_dict>, "client_id": "<uuid4>"}
  → {"prompt_id": "<id>"}

GET {host}/history/{prompt_id}
  → poll every 500ms until prompt_id key present
  → {"<id>": {"outputs": {"<node_id>": {"images": [{"filename":"...","subfolder":"","type":"output"}]}}}}

GET {host}/view?filename={f}&subfolder={s}&type=output
  → raw PNG bytes
  → retry up to 5× with 200ms backoff if 404 (file may not be written yet)
```

---

## 11. Wake-Word Pipeline (`src/voice/wakeword.py`)

```python
class WakeWordListener:
    def load(self):
        model_path = settings.voice.wake_word.model
        # openwakeword accepts both built-in names and .onnx file paths
        self.model = Model(wakeword_models=[model_path])

    def start(self, loop: asyncio.AbstractEventLoop):
        threading.Thread(target=self._run, args=(loop,), daemon=True).start()

    def _run(self, loop):
        chunk_size = 1280   # 80ms at 16kHz; openwakeword expects 16kHz int16
        with sd.InputStream(samplerate=16000, channels=1, dtype="int16",
                            blocksize=chunk_size,
                            device=settings.voice.input_device) as stream:
            while self._running:
                chunk, _ = stream.read(chunk_size)
                prediction = self.model.predict(chunk.flatten())
                if max(prediction.values()) >= settings.voice.wake_word.threshold:
                    loop.call_soon_threadsafe(self._detected_event.set)
```

If `voice.wake_word.enabled: false`, skip the listener entirely — mic button activates recording directly.

---

## 12. WebSocket Protocol

**Frontend → Backend:**
```jsonc
{"type": "message",        "conversation_id": "uuid", "text": "..."}
{"type": "voice_start",    "conversation_id": "uuid"}
{"type": "new_conversation"}
{"type": "clear_history",  "conversation_id": "uuid"}
```

**Backend → Frontend:**
```jsonc
{"type": "chunk",                "text": "..."}
{"type": "image",                "path": "/output/images/x.png", "prompt": "..."}
{"type": "tool_start",           "tool": "generate_image"}
{"type": "tool_done",            "tool": "generate_image"}
{"type": "voice_transcribed",    "text": "..."}
{"type": "status",               "state": "IDLE|LISTENING|WAKE_WORD_DETECTED|THINKING|SPEAKING"}
{"type": "conversation_created", "id": "uuid", "title": "New conversation"}
{"type": "conversation_titled",  "id": "uuid", "title": "Auto title"}
{"type": "done"}
{"type": "error",                "message": "..."}
```

Multiple browser tabs may open the same `conversation_id`. Maintain `dict[str, set[WebSocket]]` and broadcast to all subscribers.

---

## 13. Systemd Unit File

```ini
[Unit]
Description=Local LLM Assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/user/assistant
ExecStart=/home/user/.local/bin/uv run python -m src.main
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/home/user/assistant/.env

[Install]
WantedBy=default.target
```

Install:
```bash
mkdir -p ~/.config/systemd/user/
cp assistant.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now assistant
journalctl --user -fu assistant
```

---

## 14. `scripts/inspect_workflow.py`

```python
#!/usr/bin/env python3
"""Print node IDs and class types for a ComfyUI API-format workflow JSON."""
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
workflow = json.loads(path.read_text())
print(f"\n{'ID':<8} {'Class':<35} Title")
print("-" * 70)
for node_id, node in sorted(workflow.items(), key=lambda x: int(x[0])):
    title = node.get("_meta", {}).get("title", "")
    print(f"{node_id:<8} {node['class_type']:<35} {title}")
```

---

## 15. Constraints & Gotchas

1. **Plugin isolation**: Plugins must not import from each other. All shared utilities live in `src/`. Cross-plugin dependencies are not supported.

2. **Plugin setup errors**: A plugin that raises in `setup()` is skipped and logged — the application must still start. Never let one bad plugin crash the whole assistant.

3. **Health check at startup only**: `health_check()` runs once at startup. If a service goes down later, tool handlers must return descriptive error strings rather than raising exceptions. The LLM will see the error and respond appropriately.

4. **Tool name uniqueness**: Tool names across all plugins must be globally unique. Use a `{plugin_name}_{action}` prefix convention, e.g. `comfyui_generate_image`, `homeassistant_call_service`. Enforce this in `PluginRegistry.load_all()` with a clear error if a duplicate is detected.

5. **Config_key must match settings.yaml**: If a plugin declares `config_key = "jellyfin"`, there must be a `plugins.jellyfin:` section in `settings.yaml`. If the key is missing, `setup()` receives `{}` — plugins must handle this gracefully.

6. **CUDA device selection**: Always read device from config; never hardcode. ComfyUI manages its own GPU externally.

7. **Node IDs are strings**: ComfyUI node IDs in workflow JSON are always `"3"`, `"6"` etc., never integers.

8. **LoRA files are remote**: The plugin sends filenames to ComfyUI; it does not transfer files. The filename must match exactly what exists in ComfyUI's `models/loras/` directory on the ComfyUI host.

9. **SQLite async**: All DB access via `aiosqlite`. Never use synchronous `sqlite3` in async code paths.

10. **History trimming is send-only**: Trimming applies only to the message list sent to Ollama. The full history is always stored in SQLite.

11. **Wake word + keyboard coexist**: Both are always active simultaneously. They share the same agent loop and write to the same conversation.

12. **Google Drive OAuth on headless VM**: First run requires a browser. Document workaround: `python -m src.services.google_drive --auth` with X forwarding, or copy the token file from a machine with a browser.

13. **Ollama model validation**: At startup, call `GET {ollama_host}/api/tags` and confirm the configured model is present. Log a clear, actionable error if absent (include the `ollama pull` command). Models confirmed to support tool use: `qwen2.5:*`, `llama3.1:*`, `llama3.2:*`, `mistral-nemo`.

14. **`/plugins` endpoint is read-only**: It reports plugin status. It does not allow enabling/disabling plugins at runtime — that requires a config change and restart.

---

## 16. Testing Requirements

- `tests/test_plugin_loader.py`: Write a minimal stub plugin; confirm discovery, setup, tool registration, and health-check-failure graceful skip all work correctly
- `tests/test_comfyui_plugin.py`: Mock HTTP; test `patch_workflow()` with and without `lora_loader` in node_map; test polling + 404 retry; test LoRA alias resolution
- `tests/test_stt.py`: Load a short WAV; assert transcription is non-empty string
- `tests/test_persistence.py`: Create conversation; add messages; retrieve; verify order; test soft-delete; test history trimming

Run with: `uv run pytest tests/`

---

## 17. README.md Must Cover

- Prerequisites: Python 3.11+, `uv`, Ollama, ComfyUI, CUDA drivers (if applicable)
- `ollama pull qwen2.5:14b`
- `uv sync` then GPU torch reinstall
- `.env.example` → `.env`
- How to export a ComfyUI workflow in API format and find node IDs
- How to configure LoRAs
- How to set or change the wake word (built-in names, custom `.onnx`, disable)
- `uv run python -m src.main`
- Systemd install steps
- **How to write a plugin** (mirrors §8.5 — this is a first-class feature, document it prominently)
- Available built-in plugins and their config keys
- Google Drive first-run auth on headless VM
- Troubleshooting: Ollama unreachable, ComfyUI unreachable, no audio device, CUDA OOM, plugin failed to load

---

## 18. Out of Scope

- User authentication / multi-user support
- Image editing / img2img (txt2img + ComfyUI workflows only)
- Wake-word model training (document the process and link to openwakeword docs; do not implement training code)
- Plugin hot-reload at runtime (restart required after adding a plugin)
- Mobile app
- Any cloud LLM
