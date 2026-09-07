"""Registry of all known components, maintained in topological dependency order."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from .component_base import base_comp


class ComponentRegistry:
    _instance: ClassVar[ComponentRegistry | None] = None

    def __new__(cls) -> ComponentRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._comps = []
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

    def get(self, name: str) -> base_comp | None:
        for c in self._comps:
            if c.name == name:
                return c
        return None

    def names(self) -> list[str]:
        return [c.name for c in self._comps]

    def __iter__(self):
        return iter(list(self._comps))

    def __len__(self) -> int:
        return len(self._comps)

    def active_set(self, starting: set[str] | None) -> set[str]:
        """Return names of components reachable from *starting* via active deps."""
        active: set[str] = set()

        def activate(comp: base_comp) -> None:
            if comp.name in active:
                return
            active.add(comp.name)
            for dep in comp.active_deps():
                activate(dep)

        for inst in self._comps:
            if starting is None or inst.name in starting:
                activate(inst)
        return active

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
                assert self.get(dep.name) is dep, (
                    f"{inst.name}.dependencies contains unregistered instance {dep.name!r}"
                )


REGISTRY: ComponentRegistry = ComponentRegistry()
