"""Ecosystem component."""
from .configuration import configuration
from .component_internal import component
from .component_registry import REGISTRY


class comp_ecosystem(component):
    def __init__(self) -> None:
        super().__init__(
            name="ecosystem",
            dependencies=["git-repos-access"],
            configuration=configuration("edit .jejune/ecosystem-env-config and set JEJUNE_ROOT_DIR", env_vars=["JEJUNE_ROOT_DIR"], max_severity="warn"),
        )

    def check(self) -> tuple[str, str]:
        return "ok", ""


REGISTRY.add(comp_ecosystem())
