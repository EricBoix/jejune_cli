"""Deployment component (internal)."""
from .component_internal import component
from .component_registry import REGISTRY


class comp_deployment_comp(component):
    def __init__(self) -> None:
        super().__init__(name="deployment", dependencies=["catalog"])

    def check(self) -> tuple[str, str]:
        return "ok", ""


REGISTRY.add(comp_deployment_comp())
