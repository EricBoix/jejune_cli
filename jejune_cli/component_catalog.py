"""Catalog configuration component."""
from .component_with_config import conf_comp as component
from .component_registry import ComponentRegistry


class comp_catalog(component):
    def __init__(self) -> None:
        super().__init__(name="catalog", dependencies=[ComponentRegistry().get("ecosystem")])

    def check(self) -> tuple[str, str]:
        return "ok", ""


