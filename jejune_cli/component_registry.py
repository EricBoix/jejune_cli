"""Registry of all known components, maintained in topological dependency order."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .component_base import base_comp
    from .component_ext import ext_comp


class ComponentRegistry:
    def __init__(self) -> None:
        self._comps: list[base_comp] = []

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
            for dep in comp.dependencies:
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


REGISTRY: ComponentRegistry = ComponentRegistry()
