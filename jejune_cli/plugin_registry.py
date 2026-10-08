"""PluginRegistry — discovers, registers, and manages plugin packages."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
from typing import Callable

import click

from .component_registry import ComponentRegistry, _UnresolvedPlugin
from .component_with_config import ConfComp
from .configuration import Configuration
from .configuration_entry import ConfigurationEntry
from .plugin_comp import PluginComp
from .plugin_description import PluginDescription


class PluginRegistry:
    """Registry for all installed plugin packages.

    Plugin packages expose a ``PluginDescription`` instance via the
    ``"jejune.plugins"`` entry-point group.  This registry discovers them,
    registers their components in ComponentRegistry, and fires post-hooks so that
    ``app_context.py`` can wire CLI commands and roles.
    """

    def __init__(self, component_registry: ComponentRegistry) -> None:
        self._component_registry = component_registry
        self._plugins: list[PluginDescription] = []
        self._loaded: set[str] = set()
        self._post_hooks: list[Callable[[PluginDescription], None]] = []
        self._finalize_hook: Callable[[], None] | None = None
        self._plugin_repo_names: dict[str, str] = {}

    def add_post_hook(self, fn: Callable[[PluginDescription], None]) -> None:
        """Register callback invoked after each plugin is component-registered."""
        self._post_hooks.append(fn)

    def set_finalize_hook(self, fn: Callable[[], None]) -> None:
        """Register callback invoked once after all plugins are loaded."""
        self._finalize_hook = fn

    def ensure_loaded(self, name: str) -> None:
        """On-demand load: find and register a single plugin by entry-point name."""
        if name in self._loaded:
            return
        for ep in importlib.metadata.entry_points(group="jejune.plugins"):
            if ep.name == name:
                try:
                    plugin: PluginDescription = ep.load()
                    self.register_plugin_component(plugin)
                except Exception as exc:
                    click.echo(
                        f"Warning: failed to load plugin {name!r}: {exc}", err=True
                    )
                return

    def register_plugin_component(self, plugin: PluginDescription) -> None:
        """Register a plugin in ComponentRegistry and fire post-hooks.  Idempotent."""
        if plugin.name in self._loaded:
            return
        self._loaded.add(plugin.name)
        self._plugins.append(plugin)

        if plugin.component is not None:
            self._component_registry.add(plugin.component)
        else:
            existing = self._component_registry.get(plugin.name)
            if existing is None or isinstance(existing, _UnresolvedPlugin):
                comp = PluginComp(
                    name=plugin.name,
                    dependencies=plugin.required_deps or [],
                    hint=plugin.avail_hint,
                )
                self._component_registry.add(comp)
            elif plugin.avail_hint and not existing.hint:
                existing.set_hint(plugin.avail_hint)

        for dep_name in plugin.optional_deps:
            inst = self._component_registry.get(dep_name)
            if inst:
                inst.set_mandatory(False)

        if plugin.config_vars:
            inst = self._component_registry.get(plugin.name)
            if isinstance(inst, ConfComp):
                inst.set_configuration(
                    Configuration(
                        *(
                            ConfigurationEntry(v, hint=plugin.config_hint)
                            for v in plugin.config_vars
                        )
                    )
                )

        for hook in self._post_hooks:
            hook(plugin)

    def load_all(self) -> None:
        """Discover all installed plugin packages and register them.

        0. Reads ``direct_url.json`` (PEP 610) for each installed plugin to map
           repo names to ep names.  Falls back to the normalized distribution name.
        1. Iterates ``"jejune.plugins"`` entry-points, calls
           ``register_plugin_component`` for each.
        2. Resolves ``plugin_deps`` declared by built-in components.
        3. Calls the finalize hook.
        """
        # Phase 0: map repo names to plugin names.
        expected_plugin_names: set[str] = set()
        discovered: dict[str, str] = {}  # normalized repo/dist name → ep.name
        for ep in importlib.metadata.entry_points(group="jejune.plugins"):
            expected_plugin_names.add(ep.name)
            if ep.dist is None:
                continue
            direct_url_text = ep.dist.read_text("direct_url.json")
            if direct_url_text:
                try:
                    data = json.loads(direct_url_text)
                    url = data.get("url", "")
                    if url.startswith("file://"):
                        repo_name = Path(url[7:]).name
                        repo_key = repo_name.lower().replace("-", "_")
                        discovered.setdefault(repo_key, ep.name)
                        self._plugin_repo_names.setdefault(ep.name, repo_name)
                except (ValueError, KeyError):
                    pass
            # Fallback: normalized distribution name (non-editable installs)
            dist_key = ep.dist.name.lower().replace("-", "_")
            discovered.setdefault(dist_key, ep.name)
        self._component_registry.register_expected_plugin_names(expected_plugin_names)

        # Phase 1: load installed entry-points and register their components.
        for ep in importlib.metadata.entry_points(group="jejune.plugins"):
            try:
                plugin: PluginDescription = ep.load()
            except Exception as exc:
                click.echo(
                    f"Warning: failed to load plugin {ep.name!r}: {exc}", err=True
                )
                continue
            self.register_plugin_component(plugin)
            if plugin.repo_name:
                repo_key = plugin.repo_name.lower().replace("-", "_")
                discovered.setdefault(repo_key, plugin.name)
                self._plugin_repo_names.setdefault(plugin.name, plugin.repo_name)

        # Phase 2: wire resolved plugin instances into comp.dependencies.
        plugin_packages = self._component_registry.get("plugin-packages")
        for comp in self._component_registry:
            if not getattr(comp, "plugin_deps", []):
                continue
            for repo_name in comp.plugin_deps:
                plugin_name = discovered.get(repo_name.lower().replace("-", "_"))
                if plugin_name is None:
                    continue
                inst = self._component_registry.get(plugin_name)
                if (
                    inst is not None
                    and not isinstance(inst, _UnresolvedPlugin)
                    and inst not in comp.dependencies
                ):
                    comp.dependencies.append(inst)
            if (
                plugin_packages is not None
                and not isinstance(plugin_packages, _UnresolvedPlugin)
                and plugin_packages not in comp.dependencies
            ):
                comp.dependencies.append(plugin_packages)
        if any(getattr(c, "plugin_deps", []) for c in self._component_registry):
            self._component_registry._sort()

        # Phase 3: call the finalize hook.
        if self._finalize_hook is not None:
            self._finalize_hook()

    def repo_name_for_plugin(self, plugin_name: str) -> str | None:
        """Return the actual repo name for *plugin_name*, as used in plugin_deps."""
        return self._plugin_repo_names.get(plugin_name)

    def register_repo_name(self, plugin_name: str, repo_name: str) -> None:
        """Record the repo-name → plugin-name mapping (idempotent, first write wins)."""
        self._plugin_repo_names.setdefault(plugin_name, repo_name)

    def plugin_name_for_repo(self, repo_name: str) -> str | None:
        """Return installed plugin ep name for *repo_name*, or None."""
        key = repo_name.lower().replace("-", "_")
        for ep_name, repo in self._plugin_repo_names.items():
            if repo.lower().replace("-", "_") == key:
                return ep_name
        for ep in importlib.metadata.entry_points(group="jejune.plugins"):
            if ep.dist is not None:
                dist_key = ep.dist.name.lower().replace("-", "_")
                if dist_key == key:
                    return ep.name
        return None

    @property
    def plugins(self) -> list[PluginDescription]:
        return list(self._plugins)
