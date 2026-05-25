"""Thin shim: pulls all tools from PluginRegistry at runtime.

No tool definitions live here. The agent calls registry.get_ollama_tool_schemas()
and registry.get_tool_handler(name) directly.
"""

from src.plugins.registry import PluginRegistry


def get_tools_from_registry(registry: PluginRegistry):
    return registry.get_all_tools()


def get_tool_schemas_from_registry(registry: PluginRegistry):
    return registry.get_ollama_tool_schemas()


def get_handler(registry: PluginRegistry, tool_name: str):
    return registry.get_tool_handler(tool_name)