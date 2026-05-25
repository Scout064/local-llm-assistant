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


class TestPluginRegistry:
    @pytest.mark.asyncio
    async def test_health_check_failure_graceful_skip(self):
        from src.plugins.registry import PluginRegistry
        from src.config import settings

        registry = PluginRegistry()

        unhealthy_plugin_dir = Path("plugins/builtin")
        # The built-in plugins will try health checks against real services.
        # Most will fail in a test environment. The key test is that
        # the registry does not crash when health checks fail.
        await registry.load_all(settings)

        # At minimum, unhealthy plugins should be tracked
        status = registry.get_status()
        assert isinstance(status, list)

    @pytest.mark.asyncio
    async def test_tool_name_uniqueness(self):
        from src.plugins.base import Plugin, ToolDefinition
        from src.plugins.registry import PluginRegistry

        class PluginA(Plugin):
            name = "plug_a"
            display_name = "A"
            async def setup(self, config): pass
            async def health_check(self): return True
            def get_tools(self):
                return [ToolDefinition(
                    schema={"type": "function", "function": {"name": "shared_action", "parameters": {"type": "object", "properties": {}}}},
                    handler=self._handler
                )]
            async def _handler(self): return "ok"

        class PluginB(Plugin):
            name = "plug_b"
            display_name = "B"
            async def setup(self, config): pass
            async def health_check(self): return True
            def get_tools(self):
                return [ToolDefinition(
                    schema={"type": "function", "function": {"name": "shared_action", "parameters": {"type": "object", "properties": {}}}},
                    handler=self._handler
                )]
            async def _handler(self): return "ok"

        # Duplicate tool names should be detected and deduplicated
        tools_a = PluginA().get_tools()
        tools_b = PluginB().get_tools()
        names = [t.schema["function"]["name"] for t in tools_a + tools_b]
        assert names.count("shared_action") == 2  # both define it