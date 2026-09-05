"""kg-viewer containerized component."""
from .component_containerized import cont_comp
from .component_registry import REGISTRY
from .role import register_role_repos


class comp_kg_viewer(cont_comp):
    def __init__(self) -> None:
        super().__init__(
            name="kg-viewer",
            image_name="jejune-kg-graph-viewer",
            service_name="kg-graph-viewer",
            dependencies=[REGISTRY.get("ecosystem"), REGISTRY.get("docker-command")],
            hint="run `jejune deployment install`",
        )
        register_role_repos("deployer", [("jejune_kg-graph_viewer", None, "KG_GRAPH_VIEWER_CONTEXT")])

    def is_available(self) -> bool:
        return self.is_built()

    def is_running(self) -> tuple[bool, str]:
        from pathlib import Path
        deploy_name = Path(".").resolve().name.lower()
        return super().is_running(f"jejune-{deploy_name}-{self.service_name}-1")


REGISTRY.add(comp_kg_viewer())
