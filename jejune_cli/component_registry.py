"""Registry of all known components, maintained in topological dependency order."""

from __future__ import annotations

from pathlib import Path

from .component_base import BaseComp


class _UnresolvedPlugin:
    """Sentinel for a plugin component that is expected but not yet registered.

    Returned by ``ComponentRegistry.get()`` when the name is in
    ``_expected_plugin_names`` but no real component instance has been added.
    Used as an isinstance sentinel in ``plugin_registry`` to distinguish
    "known but absent" from a real component.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name


class ComponentRegistry:
    def __init__(self) -> None:
        self._comps: list[BaseComp] = []
        self._expected_plugin_names: set[str] = set()

    def register_expected_plugin_names(self, names: set[str]) -> None:
        """Add *names* to the set of plugin component names expected to be loaded.

        Must be called before any code invokes ``get()`` with a plugin name,
        so that ``get()`` can return a ``_UnresolvedPlugin`` proxy rather than ``None``
        for components that are known but not yet registered.  Calling this
        method multiple times is safe — it accumulates names.
        """
        self._expected_plugin_names.update(names)

    def add(self, comp: BaseComp) -> None:
        self._comps.append(comp)
        self._sort()

    def _sort(self) -> None:
        """Re-order in topological dependency order (deps before dependents)."""
        by_name = {c.name: c for c in self._comps}
        comp_set = set(by_name)
        visited: set[str] = set()
        result: list[BaseComp] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            comp = by_name.get(name)
            if comp is None:
                return
            for dep in comp.ordering_deps():
                if dep is None:
                    continue
                if dep.name in comp_set:
                    visit(dep.name)
            result.append(by_name[name])

        for name in list(by_name):
            visit(name)
        self._comps = result

    def get(self, name: str) -> "BaseComp | _UnresolvedPlugin | None":
        for c in self._comps:
            if c.name == name:
                return c
        if name in self._expected_plugin_names:
            return _UnresolvedPlugin(name)
        return None

    def unfulfilled_plugin_names(self) -> set[str]:
        """Return expected plugin names that have not yet been added as components."""
        registered = {c.name for c in self._comps}
        return self._expected_plugin_names - registered

    def names(self) -> list[str]:
        return [c.name for c in self._comps]

    def __iter__(self):
        return iter(list(self._comps))

    def __len__(self) -> int:
        return len(self._comps)

    def sorted_active_set(
        self, starting: "frozenset[BaseComp] | None"
    ) -> "list[BaseComp]":
        """Components reachable from *starting* via active deps, in topological order."""
        active: set[BaseComp] = set()

        def activate(comp: BaseComp) -> None:
            if comp in active:
                return
            active.add(comp)
            for dep in comp.active_deps():
                activate(dep)

        for inst in self._comps:
            if starting is None or inst in starting:
                activate(inst)
        return self.sorted_subset(list(active))

    def sorted_subset(self, components: list[BaseComp]) -> list[BaseComp]:
        """Return *components* in the registry's topological order."""
        comp_set = {c.name for c in components}
        ordered = [c for c in self._comps if c.name in comp_set]
        ordered_names = {c.name for c in ordered}
        ordered += [c for c in components if c.name not in ordered_names]
        return ordered

    def load_all_configurations(self, base_dir: Path) -> None:
        """Load env-file sources for every component that has a configuration."""
        for comp in self._comps:
            if hasattr(comp, "configuration"):
                comp.configuration.load(base_dir)

    def validate(self) -> None:
        """Assert every dep instance referenced by a component is registered."""
        for inst in self._comps:
            for dep in inst.all_deps():
                if isinstance(dep, _UnresolvedPlugin):
                    continue
                if self.get(dep.name) is not dep:
                    raise RuntimeError(
                        f"{inst.name}.dependencies contains unregistered instance {dep.name!r}"
                    )
