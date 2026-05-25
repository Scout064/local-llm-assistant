from __future__ import annotations

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

        seen_names: set[str] = set()
        seen_tool_names: set[str] = set()

        for cls in plugin_classes:
            instance = cls()

            if instance.name in seen_names:
                log.error("plugin_duplicate_name", name=instance.name)
                continue
            seen_names.add(instance.name)

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
            for tool in tools:
                tool_name = tool.schema["function"]["name"]
                if tool_name in seen_tool_names:
                    log.error("plugin_duplicate_tool", tool=tool_name, plugin=instance.name)
                    continue
                seen_tool_names.add(tool_name)
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

    def get_tool_handler(self, tool_name: str):
        for tool in self._tools:
            if tool.schema["function"]["name"] == tool_name:
                return tool.handler
        return None

    def get_status(self) -> list[dict]:
        """For the /plugins web endpoint."""
        failed = set(self._failed)
        result = []
        for p in self._plugins:
            plugin_tools = p.get_tools()
            plugin_tool_names = [t.schema["function"]["name"] for t in plugin_tools]
            result.append({
                "name": p.name,
                "display_name": p.display_name,
                "version": p.version,
                "description": p.description,
                "status": "unhealthy" if p.name in failed else "ok",
                "tools": plugin_tool_names,
            })
        return result