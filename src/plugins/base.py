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