"""Deployment component (internal)."""
from .component_internal import component


class comp_deployment(component):
    def __init__(self) -> None:
        super().__init__(
            name="deployment",
            dependencies=[
                type(self).registry.get("catalog"),
                type(self).registry.get("docs-server"),
                type(self).registry.get("kg-viewer"),
                type(self).registry.get("md-browser"),
            ],
            hint="run `jejune deployment install`",
        )
        type(self).registry.add(self)

    def check(self) -> tuple[str, str]:
        for dep in self.dependencies:
            if not dep.is_available():
                return "error", "images not built"
        return "ok", ""


comp_deployment()
