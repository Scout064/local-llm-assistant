"""Test plugin loader: discovery, setup, tool registration, health-check-failure graceful skip."""
import sys
import types
import tempfile
from pathlib import Path

import pytest

from src.plugins.base import Plugin, ToolDefinition
from src.plugins.loader import discover_plugins, _load_plugin_class


class TestLoadPluginClass:
    def test_loads_with_plugin_class_export(self, tmp_path):
        pdir = tmp_path / "myplug"
        pdir.mkdir()
        (pdir / "plugin.py").write_text('''
from src.plugins.base import Plugin, ToolDefinition

class MyPlug(Plugin):
    name = "myplug"
    display_name = "My Plug"
    async def health_check(self): return True
    def get_tools(self): return []

PLUGIN_CLASS = MyPlug
''')
        cls = _load_plugin_class(pdir / "plugin.py", "myplug")
        assert cls is not None
        assert cls.name == "myplug"

    def test_returns_none_for_empty_module(self, tmp_path):
        pdir = tmp_path / "empty"
        pdir.mkdir()
        (pdir / "plugin.py").write_text("x = 1\n")
        cls = _load_plugin_class(pdir / "plugin.py", "empty")
        assert cls is None

    def test_rejects_multiple_subclasses(self, tmp_path):
        pdir = tmp_path / "multi"
        pdir.mkdir()
        (pdir / "plugin.py").write_text('''
from src.plugins.base import Plugin, ToolDefinition

class PlugA(Plugin):
    name = "a"
    display_name = "A"
    async def health_check(self): return True
    def get_tools(self): return []

class PlugB(Plugin):
    name = "b"
    display_name = "B"
    async def health_check(self): return True
    def get_tools(self): return []
''')
        with pytest.raises(ValueError, match="Multiple Plugin subclasses"):
            _load_plugin_class(pdir / "plugin.py", "multi")


class TestDiscoverPlugins:
    def test_discovers_plugin(self, tmp_path):
        stub_dir = tmp_path / "stub_service"
        stub_dir.mkdir()
        (stub_dir / "__init__.py").write_text("")
        (stub_dir / "plugin.py").write_text('''
from src.plugins.base import Plugin, ToolDefinition

class StubPlugin(Plugin):
    name = "stub_service"
    display_name = "Stub Service"
    async def health_check(self): return True
    def get_tools(self): return []

PLUGIN_CLASS = StubPlugin
''')
        found = discover_plugins([tmp_path])
        assert len(found) == 1
        assert found[0].name == "stub_service"

    def test_skips_underscore_dirs(self, tmp_path):
        underscore_dir = tmp_path / "__pycache__"
        underscore_dir.mkdir()
        found = discover_plugins([tmp_path])
        assert len(found) == 0

    def test_skips_dirs_without_plugin_py(self, tmp_path):
        empty_dir = tmp_path / "no_plugin"
        empty_dir.mkdir()
        (empty_dir / "__init__.py").write_text("")
        found = discover_plugins([tmp_path])
        assert len(found) == 0


class TestPluginRegistryHealthCheck:
    @pytest.mark.asyncio
    async def test_unhealthy_plugin_excluded_from_tools(self, tmp_path):
        """A plugin whose health_check returns False should be registered
        for status but NOT contribute tools."""
        from src.plugins.registry import PluginRegistry

        unhealthy_dir = tmp_path / "unhealthy_svc"
        unhealthy_dir.mkdir()
        (unhealthy_dir / "__init__.py").write_text("")
        (unhealthy_dir / "plugin.py").write_text('''
from src.plugins.base import Plugin, ToolDefinition

class UnhealthyPlugin(Plugin):
    name = "unhealthy_svc"
    display_name = "Unhealthy Service"
    config_key = None
    async def setup(self, config): pass
    async def health_check(self): return False
    def get_tools(self):
        return [ToolDefinition(
            schema={"type": "function", "function": {"name": "unhealthy_action", "parameters": {"type": "object", "properties": {}}}},
            handler=self._handler,
        )]
    async def _handler(self): return "ok"

PLUGIN_CLASS = UnhealthyPlugin
''')

        registry = PluginRegistry()
        original_discover = sys.modules["src.plugins.registry"].discover_plugins
        sys.modules["src.plugins.registry"].discover_plugins = lambda dirs: discover_plugins([tmp_path])
        try:
            from src.config import settings
            await registry.load_all(settings)
        finally:
            sys.modules["src.plugins.registry"].discover_plugins = original_discover

        assert "unhealthy_svc" in registry._failed
        assert len(registry.get_all_tools()) == 0
        status = registry.get_status()
        assert len(status) == 1
        assert status[0]["status"] == "unhealthy"


class TestPluginRegistryToolDedup:
    @pytest.mark.asyncio
    async def test_duplicate_tool_name_across_plugins_filtered(self, tmp_path):
        """When two plugins define a tool with the same name, only the first is kept."""
        from src.plugins.registry import PluginRegistry

        plug_a_dir = tmp_path / "plug_a"
        plug_a_dir.mkdir()
        (plug_a_dir / "__init__.py").write_text("")
        (plug_a_dir / "plugin.py").write_text('''
from src.plugins.base import Plugin, ToolDefinition
class PlugA(Plugin):
    name = "plug_a"
    display_name = "A"
    config_key = None
    async def setup(self, config): pass
    async def health_check(self): return True
    def get_tools(self):
        return [ToolDefinition(
            schema={"type": "function", "function": {"name": "shared_action", "parameters": {"type": "object", "properties": {}}}},
            handler=self._h,
        )]
    async def _h(self): return "a"
PLUGIN_CLASS = PlugA
''')

        plug_b_dir = tmp_path / "plug_b"
        plug_b_dir.mkdir()
        (plug_b_dir / "__init__.py").write_text("")
        (plug_b_dir / "plugin.py").write_text('''
from src.plugins.base import Plugin, ToolDefinition
class PlugB(Plugin):
    name = "plug_b"
    display_name = "B"
    config_key = None
    async def setup(self, config): pass
    async def health_check(self): return True
    def get_tools(self):
        return [ToolDefinition(
            schema={"type": "function", "function": {"name": "shared_action", "parameters": {"type": "object", "properties": {}}}},
            handler=self._h,
        )]
    async def _h(self): return "b"
PLUGIN_CLASS = PlugB
''')

        registry = PluginRegistry()
        sys.modules["src.plugins.registry"].discover_plugins = lambda dirs: discover_plugins([tmp_path])
        try:
            from src.config import settings
            await registry.load_all(settings)
        finally:
            del sys.modules["src.plugins.registry"].discover_plugins

        tools = registry.get_all_tools()
        tool_names = [t.schema["function"]["name"] for t in tools]
        assert len(tools) == 1
        assert "shared_action" in tool_names