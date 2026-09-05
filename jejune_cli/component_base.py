"""Abstract base class for all jejune components."""
from abc import ABC, abstractmethod
from typing import Callable, ClassVar

from .component_registry import ComponentRegistry


class base_comp(ABC):
    registry: ClassVar[ComponentRegistry] = ComponentRegistry()

    def __init__(
        self,
        name: str,
        dependencies: "list[base_comp] | None" = None,
        optional_dependencies: "list[base_comp] | None" = None,
        hint: str | None = None,
    ) -> None:
        self.name = name
        self.visible: Callable[[], bool] | None = None
        self.dependencies: list[base_comp] = dependencies or []
        # Optional dependencies depend on the configuration choices
        self.optional_dependencies: list[base_comp] = optional_dependencies or []
        self.hint = hint

    @abstractmethod
    def check(self) -> tuple[str, str]:
        """Return (status, message) where status is 'ok', 'warn', or 'error'."""
        ...

    def is_available(self) -> bool:
        """Return True when check() reports ok or warn (non-error)."""
        return self.check()[0] != "error"

    @staticmethod
    def initialize_registry() -> None:
        from . import (  # noqa: F401
            component_ext_network,
            component_ext_command_git,
            component_ext_command_docker,
            component_ext_command_uv,
            component_ext_server_pypi,
            component_ext_server_docker_hub,
            component_ext_server_git,
            component_ext_server_llm,
            component_ext_server_llm_observability,
            component_ext_extensions,
            component_ecosystem,
            component_catalog,
            component_manifest,
            component_cont_docs_server,
            component_cont_kg_viewer,
            component_cont_md_browser,
            component_cont_convert,
            component_cont_neo4j,
            component_cont_graph,
            component_deployment,
        )
