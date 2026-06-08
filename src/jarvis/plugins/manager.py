from __future__ import annotations

import asyncio
import importlib
import logging
from pathlib import Path
from typing import Any

import yaml

from jarvis.plugins.base import Plugin, PluginHook, PluginMetadata

logger = logging.getLogger(__name__)


class PluginManager:
    """Manages plugin lifecycle and hook dispatch.

    Features:
    - Plugin registration and lifecycle (load/unload)
    - Hook dispatch (emit events, plugins respond)
    - Plugin dependency resolution
    - Plugin from YAML manifest
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._hooks: dict[PluginHook, list[tuple[str, Any]]] = {
            hook: [] for hook in PluginHook
        }

    # ------------------------------------------------------------------
    # Plugin lifecycle
    # ------------------------------------------------------------------

    async def load(self, plugin: Plugin) -> None:
        """Load and activate a plugin."""
        name = plugin.metadata.name
        if name in self._plugins:
            logger.warning("Plugin %s already loaded, skipping", name)
            return

        # Check dependencies
        for dep in plugin.metadata.dependencies:
            if dep not in self._plugins:
                raise RuntimeError(
                    f"Plugin '{name}' depends on '{dep}' which is not loaded"
                )

        # Register hooks
        for hook, callback in plugin.get_hooks().items():
            self._hooks[hook].append((name, callback))

        await plugin.on_load()
        self._plugins[name] = plugin
        logger.info("Loaded plugin: %s v%s", name, plugin.metadata.version)

    async def unload(self, name: str) -> None:
        """Unload a plugin by name."""
        plugin = self._plugins.get(name)
        if plugin is None:
            logger.warning("Plugin %s not found", name)
            return

        # Remove hooks
        for hook in PluginHook:
            self._hooks[hook] = [
                (n, cb) for n, cb in self._hooks[hook] if n != name
            ]

        await plugin.on_unload()
        del self._plugins[name]
        logger.info("Unloaded plugin: %s", name)

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return info dicts for every loaded plugin."""
        return [
            {
                "name": p.metadata.name,
                "version": p.metadata.version,
                "description": p.metadata.description,
                "author": p.metadata.author,
                "enabled": p.metadata.enabled,
            }
            for p in self._plugins.values()
        ]

    # ------------------------------------------------------------------
    # Hook dispatch
    # ------------------------------------------------------------------

    async def emit(self, hook: PluginHook, **kwargs: Any) -> list[Any]:
        """Dispatch a hook to all registered plugins.

        Returns a list of results from each handler.
        """
        results: list[Any] = []
        for plugin_name, callback in self._hooks.get(hook, []):
            try:
                result = callback(**kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                results.append(result)
            except Exception:
                logger.exception(
                    "Hook %s failed in plugin %s", hook.value, plugin_name
                )
        return results

    # ------------------------------------------------------------------
    # Directory loading
    # ------------------------------------------------------------------

    async def load_directory(self, path: str | Path) -> int:
        """Load all plugins from a directory of YAML manifests.

        Each YAML file should contain:
          name, version, description, entry_point (dotted module path)

        Returns the number of plugins loaded.
        """
        directory = Path(path)
        if not directory.is_dir():
            logger.warning("Plugin directory does not exist: %s", directory)
            return 0

        loaded = 0
        for manifest_path in sorted(directory.glob("*.yaml")):
            try:
                data = yaml.safe_load(manifest_path.read_text())
                if not data or "entry_point" not in data:
                    logger.warning("Skipping invalid manifest: %s", manifest_path)
                    continue

                metadata = PluginMetadata(**{
                    k: v for k, v in data.items() if k in PluginMetadata.model_fields
                })
                module = importlib.import_module(data["entry_point"])
                plugin_cls = getattr(module, data.get("class_name", "PluginImpl"))
                plugin: Plugin = plugin_cls()
                # Override metadata if the class doesn't set it from the manifest
                await self.load(plugin)
                loaded += 1
            except Exception:
                logger.exception("Failed to load plugin from %s", manifest_path)

        logger.info("Loaded %d plugins from %s", loaded, directory)
        return loaded
