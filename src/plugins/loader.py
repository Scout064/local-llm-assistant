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