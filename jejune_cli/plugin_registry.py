"""PluginRegistry singleton — discovers, registers, and manages plugin packages."""
from __future__ import annotations

import importlib.metadata
from typing import Callable, ClassVar

import click

from .plugin_description import plugin_description


_PluginCompClass: type | None = None


def _get_plugin_comp_class() -> type:
    global _PluginCompClass
    if _PluginCompClass is None:
        from .component_with_config import conf_comp
        from .component_registry import ComponentRegistry

        class _PC(conf_comp):
            def __init__(self_, **kwargs):
                super().__init__(**kwargs)
                ComponentRegistry().add(self_)

            def check(self_) -> tuple[str, str]:
                return "ok", ""

        _PluginCompClass = _PC
    return _PluginCompClass


class PluginRegistry:
    """Singleton registry for all installed plugin packages.

    Plugin packages expose a ``plugin_description`` instance via the
    ``"jejune.plugins"`` entry-point group.  This registry discovers them,
    registers their components in COMP_REGISTRY, and fires post-hooks so that
    ``main.py`` can wire CLI commands and roles without creating a circular
    import.
    """

    _instance: ClassVar[PluginRegistry | None] = None

    def __new__(cls) -> PluginRegistry:
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._plugins: list[plugin_description] = []
            inst._loaded: set[str] = set()
            inst._post_hooks: list[Callable[[plugin_description], None]] = []
            inst._finalize_hook: Callable[[], None] | None = None
            cls._instance = inst
        return cls._instance

    def add_post_hook(self, fn: Callable[[plugin_description], None]) -> None:
        """Register callback invoked after each plugin is component-registered.

        Used by ``main.py`` to wire ``cli.add_command`` and role registration
        without importing CLI state into this module.
        """
        self._post_hooks.append(fn)

    def set_finalize_hook(self, fn: Callable[[], None]) -> None:
        """Register callback invoked once after all plugins are loaded.

        Used by ``main.py`` to update active role / help sections after the
        full plugin load pass completes.
        """
        self._finalize_hook = fn

    def ensure_loaded(self, name: str) -> None:
        """On-demand load: find and register a single plugin by entry-point name."""
        if name in self._loaded:
            return
        for ep in importlib.metadata.entry_points(group="jejune.plugins"):
            if ep.name == name:
                try:
                    plugin: plugin_description = ep.load()
                    self.register_plugin_component(plugin)
                except Exception as exc:
                    click.echo(
                        f"Warning: failed to load plugin {name!r}: {exc}", err=True
                    )
                return

    def register_plugin_component(self, plugin: plugin_description) -> None:
        """Register a plugin in COMP_REGISTRY and fire post-hooks.  Idempotent."""
        if plugin.name in self._loaded:
            return
        self._loaded.add(plugin.name)
        self._plugins.append(plugin)

        from .component_registry import ComponentRegistry, _LazyComp

        reg = ComponentRegistry()
        if plugin.component is not None:
            reg.add(plugin.component)
        else:
            existing = reg.get(plugin.name)
            if existing is None or isinstance(existing, _LazyComp):
                PC = _get_plugin_comp_class()
                PC(
                    name=plugin.name,
                    dependencies=plugin.required_deps or [],
                    hint=plugin.avail_hint,
                )
            elif plugin.avail_hint and not existing.hint:
                existing.hint = plugin.avail_hint

        for dep_name in plugin.optional_deps:
            inst = reg.get(dep_name)
            if inst:
                inst.mandatory = False

        if plugin.config_vars:
            inst = reg.get(plugin.name)
            if inst is not None and hasattr(inst, "configuration"):
                inst.configuration.env_vars = plugin.config_vars
                inst.configuration.hint = plugin.config_hint

        from .plugin_package_catalog import PLUGIN_PACKAGE_CATALOG
        PLUGIN_PACKAGE_CATALOG.register(plugin)

        for hook in self._post_hooks:
            hook(plugin)

    def load_all(self) -> None:
        """Discover all installed plugin packages and register them.

        1. Iterates ``"jejune.plugins"`` entry-points and calls
           ``register_plugin_component`` for each.
        2. Resolves ``plugin_deps`` declared by built-in components (phase-2
           dependency resolution).
        3. Calls the finalize hook so ``main.py`` can update active role state.
        """
        for ep in importlib.metadata.entry_points(group="jejune.plugins"):
            try:
                plugin: plugin_description = ep.load()
            except Exception as exc:
                click.echo(
                    f"Warning: failed to load plugin {ep.name!r}: {exc}", err=True
                )
                continue
            self.register_plugin_component(plugin)

        from .component_registry import ComponentRegistry, _LazyComp

        reg = ComponentRegistry()
        for comp in reg:
            for pname in getattr(comp, "plugin_deps", []):
                inst = reg.get(pname)
                if inst is not None and not isinstance(inst, _LazyComp) and inst not in comp.dependencies:
                    comp.dependencies.append(inst)
        if any(getattr(c, "plugin_deps", []) for c in reg):
            reg._sort()

        if self._finalize_hook is not None:
            self._finalize_hook()

    @property
    def plugins(self) -> list[plugin_description]:
        return list(self._plugins)


PLUGIN_REGISTRY = PluginRegistry()
