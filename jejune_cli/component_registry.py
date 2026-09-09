"""Registry of all known components, maintained in topological dependency order."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from .component_base import base_comp


class _LazyComp:
    """Proxy for a plugin-contributed component not yet loaded.

    Returned by ``ComponentRegistry.get()`` when the name is declared as a
    ``plugin_dep`` by some component but the plugin has not been loaded yet.
    Resolves transparently on first attribute access once the plugin is loaded.
    """

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_resolved", None)

    @property
    def name(self) -> str:
        return object.__getattribute__(self, "_name")

    def _resolve(self) -> "base_comp | None":
        cached = object.__getattribute__(self, "_resolved")
        if cached is not None:
            return cached
        inst = ComponentRegistry().get(object.__getattribute__(self, "_name"))
        if inst is not None and not isinstance(inst, _LazyComp):
            object.__setattr__(self, "_resolved", inst)
            return inst
        return None

    def __getattr__(self, attr: str):
        resolved = self._resolve()
        if resolved is None:
            raise AttributeError(
                f"Plugin component {self.name!r} is not yet loaded"
            )
        return getattr(resolved, attr)


class ComponentRegistry:
    _instance: ClassVar[ComponentRegistry | None] = None

    def __new__(cls) -> ComponentRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._comps = []
            cls._instance._comps.append(comp_network())
            cls._instance._comps.append(comp_command_git())
            cls._instance._comps.append(DOCKER_COMMAND)
            cls._instance._comps.append(comp_command_uv())
            cls._instance._comps.append(comp_server_pypi())
            cls._instance._comps.append(comp_server_docker_hub())
            cls._instance._comps.append(comp_server_git())
            cls._instance._comps.append(comp_server_llm())
            cls._instance._comps.append(comp_server_llm_observability())
            cls._instance._comps.append(comp_plugin_packages())
            cls._instance._comps.append(comp_ecosystem())
            cls._instance._comps.append(comp_catalog())
            cls._instance._comps.append(comp_manifest())
            cls._instance._comps.append(comp_convert())
            cls._instance._comps.append(comp_neo4j())
            cls._instance._comps.append(comp_graph())
            cls._instance._comps.append(comp_neo4j_to_rdf_ttl())
            cls._instance._comps.append(comp_deployment())
            cls._instance._sort()
            cls._instance.validate()
        return cls._instance

    def add(self, comp: base_comp) -> None:
        self._comps.append(comp)
        self._sort()

    def _sort(self) -> None:
        """Re-order in topological dependency order (deps before dependents)."""
        by_name = {c.name: c for c in self._comps}
        comp_set = set(by_name)
        visited: set[str] = set()
        result: list[base_comp] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            comp = by_name.get(name)
            if comp is None:
                return
            for dep in comp.ordering_deps():
                if dep.name in comp_set:
                    visit(dep.name)
            result.append(by_name[name])

        for name in list(by_name):
            visit(name)
        self._comps = result

    def get(self, name: str) -> "base_comp | _LazyComp | None":
        for c in self._comps:
            if c.name == name:
                return c
        if any(name in getattr(c, "plugin_deps", []) for c in self._comps):
            return _LazyComp(name)
        return None

    def names(self) -> list[str]:
        return [c.name for c in self._comps]

    def __iter__(self):
        return iter(list(self._comps))

    def __len__(self) -> int:
        return len(self._comps)

    def sorted_active_set(
        self, starting: "frozenset[base_comp] | None"
    ) -> "list[base_comp]":
        """Components reachable from *starting* via active deps, in topological order."""
        active: set[base_comp] = set()

        def activate(comp: base_comp) -> None:
            if comp in active:
                return
            active.add(comp)
            for dep in comp.active_deps():
                activate(dep)

        for inst in self._comps:
            if starting is None or inst in starting:
                activate(inst)
        return self.sorted_subset(list(active))

    def sorted_subset(self, components: list[base_comp]) -> list[base_comp]:
        """Return *components* in the registry's topological order."""
        comp_set = {c.name for c in components}
        ordered = [c for c in self._comps if c.name in comp_set]
        ordered_names = {c.name for c in ordered}
        ordered += [c for c in components if c.name not in ordered_names]
        return ordered

    def validate(self) -> None:
        """Assert every dep instance referenced by a component is registered."""
        for inst in self._comps:
            for dep in inst.all_deps():
                if isinstance(dep, _LazyComp):
                    continue
                assert (
                    self.get(dep.name) is dep
                ), f"{inst.name}.dependencies contains unregistered instance {dep.name!r}"


# Component class imports — placed after ComponentRegistry to avoid circular
# import (component modules do `from .component_registry import
# ComponentRegistry` at load time).
from .component_ext_network import comp_network
from .component_ext_command_git import comp_command_git
from .component_ext_command_docker import DOCKER_COMMAND
from .component_ext_command_uv import comp_command_uv
from .component_ext_server_pypi import comp_server_pypi
from .component_ext_server_docker_hub import comp_server_docker_hub
from .component_ext_server_git import comp_server_git
from .component_ext_server_llm import comp_server_llm
from .component_ext_server_llm_observability import comp_server_llm_observability
from .component_ext_plugin_packages import comp_plugin_packages
from .component_ecosystem import comp_ecosystem
from .component_catalog import comp_catalog
from .component_manifest import comp_manifest
from .component_cont_convert import comp_convert
from .component_cont_neo4j import comp_neo4j
from .component_cont_graph import comp_graph
from .component_cont_neo4j_to_rdf_ttl import comp_neo4j_to_rdf_ttl
from .component_deployment import comp_deployment

REGISTRY: ComponentRegistry = ComponentRegistry()
