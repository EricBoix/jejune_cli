"""Catalog configuration component."""
from .component_internal import component
from .component_registry import REGISTRY


class comp_catalog(component):
    def __init__(self) -> None:
        super().__init__(name="catalog", dependencies=["ecosystem"])

    def check(self) -> tuple[str, str]:
        return "ok", ""


REGISTRY.add(comp_catalog())
