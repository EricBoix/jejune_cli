"""Deployment component (internal)."""
from .component_with_config import conf_comp as component
from .component_registry import ComponentRegistry


class comp_deployment(component):
    def __init__(self) -> None:
        super().__init__(
            name="deployment",
            dependencies=[
                ComponentRegistry().get("catalog"),
                ComponentRegistry().get("docs-server"),
                ComponentRegistry().get("kg-viewer"),
                ComponentRegistry().get("md-browser"),
            ],
            hint="run `jejune deployment install`",
        )

    def check(self) -> tuple[str, str]:
        for dep in self.dependencies:
            if not dep.is_available():
                return "error", "images not built"
        return "ok", ""


