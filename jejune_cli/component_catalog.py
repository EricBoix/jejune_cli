"""Catalog configuration component."""
from .component_internal import component


class comp_catalog(component):
    def __init__(self) -> None:
        super().__init__(name="catalog", dependencies=[type(self).registry.get("ecosystem")])
        type(self).registry.add(self)

    def check(self) -> tuple[str, str]:
        return "ok", ""


comp_catalog()
