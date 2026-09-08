"""md-browser containerized component."""
from .component_containerized import cont_comp
from .component_registry import ComponentRegistry


class comp_md_browser(cont_comp):
    def __init__(self) -> None:
        super().__init__(
            name="md-browser",
            image_name="jejune:markdown-browser",
            service_name="markdown-browser",
            dependencies=[ComponentRegistry().get("ecosystem")],
            hint="run `jejune deployment install`",
        )
        self.repos = [("jejune_markdown_browser", "DockerContext", "MARKDOWN_BROWSER_CONTEXT")]

    def is_available(self) -> bool:
        return self.is_built()

    def is_running(self) -> tuple[bool, str]:
        from pathlib import Path
        deploy_name = Path(".").resolve().name.lower()
        return super().is_running(f"jejune-{deploy_name}-{self.service_name}-1")


