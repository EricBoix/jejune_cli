"""Deployment component (internal)."""
from .component_internal import component
from .component_registry import REGISTRY


class comp_deployment(component):
    def __init__(self) -> None:
        super().__init__(
            name="deployment",
            dependencies=[
                REGISTRY.get("catalog"),
                REGISTRY.get("docs-server"),
                REGISTRY.get("kg-viewer"),
                REGISTRY.get("md-browser"),
            ],
            hint="run `jejune deployment install`",
        )

    def check(self) -> tuple[str, str]:
        for dep in self.dependencies:
            if not dep.is_available():
                return "error", "images not built"
        return "ok", ""


REGISTRY.add(comp_deployment())
