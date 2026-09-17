"""Role dataclass and workspace-detection helpers for jejune_cli."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .component_base import base_comp


@dataclass
class Role:
    name: str
    component_names: tuple[str, ...]
    includes: tuple[str, ...]
    section_title: str
    detector: Callable[[], bool] | None = None
    description: str = ""
    is_abstract: bool = False
    extra_commands: tuple[str, ...] = ()

    @property
    def components(self) -> "frozenset[base_comp]":
        from .component_registry import REGISTRY as COMP_REGISTRY
        return frozenset(filter(None, (COMP_REGISTRY.get(n) for n in self.component_names)))

    @property
    def cli_commands(self) -> list[str]:
        from .component_registry import REGISTRY as COMP_REGISTRY
        return [
            comp.cli_name
            for name in self.component_names
            if (comp := COMP_REGISTRY.get(name)) is not None and comp.cli_name is not None
        ] + list(self.extra_commands)

    def __bool__(self) -> bool:
        return bool(self.name)

    def is_deployer(self) -> bool:
        return self.name == "deployer" and self.detector is not None and self.detector()

    def is_doc_steward(self) -> bool:
        return (
            self.name == "doc-steward" and self.detector is not None and self.detector()
        )

    @staticmethod
    def _is_doc_steward_cwd() -> bool:
        return (Path.cwd() / "manifest.yaml").is_file()

    @staticmethod
    def is_deployer_cwd() -> bool:
        cwd = Path.cwd()
        return (cwd / "docker-compose.yml").is_file() and (cwd / "catalog.yaml").is_file()


NO_ROLE = Role(name="", component_names=(), includes=(), section_title="")

