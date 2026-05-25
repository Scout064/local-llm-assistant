# Writing a Plugin

A plugin is a directory containing at least `plugin.py` and `__init__.py`. It may have
as many additional files as needed (e.g. `service.py`, `tools.py`).

## Plugin Structure

```
plugins/
├── builtin/                    ← ships with the project
│   └── my_service/
│       ├── __init__.py
│       ├── plugin.py           ← exports PLUGIN_CLASS
│       ├── service.py          ← HTTP client / API wrapper
│       └── tools.py            ← tool definitions + handlers
│
└── community/                  ← user-added plugins (gitignored)
    └── jellyfin/
        ├── __init__.py
        ├── plugin.py
        └── service.py
```

## Minimal Plugin Template

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
        # Return True if the service is reachable
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.host}/health", timeout=3.0)
                return resp.status_code == 200
        except Exception:
            return False

    def get_tools(self) -> list[ToolDefinition]:
        from my_service.tools import my_tool
        return [my_tool(self)]

    async def teardown(self) -> None:
        pass  # close connections


PLUGIN_CLASS = MyServicePlugin
```

## How Plugins Are Discovered

1. `PluginRegistry` scans `plugins/builtin/` first, then directories listed in
   `settings.plugins.extra_dirs`
2. Each subdirectory containing a `plugin.py` is loaded
3. The loader finds the `Plugin` subclass (or reads `PLUGIN_CLASS` if explicitly exported)
4. `setup(config)` is called with the plugin's config from `settings.yaml`
5. `health_check()` is called — if it fails, tools are disabled but the plugin is still registered
6. `get_tools()` is called to register tool schemas and handlers

## Configuration

Add a section to `config/settings.yaml` under `plugins:` matching the plugin's `config_key`:

```yaml
plugins:
  my_service:
    host: "http://my-service.local:9000"
    api_key: "${MY_SERVICE_API_KEY}"
```

## Important Rules

- **Plugins must not import from each other**. All shared utilities live in `src/`.
- **Tool names must be globally unique**. Use the `{plugin_name}_{action}` convention.
- **One bad plugin must not crash the assistant**. Setup errors are logged and skipped.
- **Health check runs at startup only**. If a service goes down later, tool handlers should return error strings, not raise exceptions.