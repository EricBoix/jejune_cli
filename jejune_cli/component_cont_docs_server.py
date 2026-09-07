"""docs-server containerized component."""
from .component_containerized import cont_comp
from .component_registry import ComponentRegistry


class comp_docs_server(cont_comp):
    def __init__(self) -> None:
        super().__init__(
            name="docs-server",
            image_name="jejune-docs-server",
            service_name="docs-server",
            dependencies=[ComponentRegistry().get("ecosystem"), ComponentRegistry().get("docker-command")],
            hint="run `jejune deployment install`",
        )
        self.repos = [("jejune_docs_server", "DockerContext", "DOCS_SERVER_CONTEXT")]

    def is_available(self) -> bool:
        return self.is_built()

    def is_running(self) -> tuple[bool, str]:
        from pathlib import Path
        deploy_name = Path(".").resolve().name.lower()
        return super().is_running(f"jejune-{deploy_name}-{self.service_name}-1")


