"""kg-viewer containerized component."""
from .component_containerized import cont_comp
from .role import register_role_repos


class comp_kg_viewer(cont_comp):
    def __init__(self) -> None:
        super().__init__(
            name="kg-viewer",
            image_name="jejune-kg-graph-viewer",
            service_name="kg-graph-viewer",
            dependencies=[type(self).registry.get("ecosystem"), type(self).registry.get("docker-command")],
            hint="run `jejune deployment install`",
        )
        register_role_repos("deployer", [("jejune_kg-graph_viewer", None, "KG_GRAPH_VIEWER_CONTEXT")])
        type(self).registry.add(self)

    def is_available(self) -> bool:
        return self.is_built()

    def is_running(self) -> tuple[bool, str]:
        from pathlib import Path
        deploy_name = Path(".").resolve().name.lower()
        return super().is_running(f"jejune-{deploy_name}-{self.service_name}-1")


comp_kg_viewer()
