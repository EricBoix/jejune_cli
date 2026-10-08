"""Role dataclass and workspace-detection helpers for jejune_cli."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, ClassVar

from ._package_paths import CatalogConfig


@dataclass
class Role:
    NONE: ClassVar["Role"]

    name: str
    component_names: tuple[str, ...]
    includes: tuple[str, ...]
    section_title: str
    detector: Callable[[], bool] | None = None
    description: str = ""
    is_abstract: bool = False
    extra_commands: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.name)

    def matches(self, name: str) -> bool:
        return self.name == name

    def is_deployer(self) -> bool:
        return self.matches("deployer")

    def is_doc_steward(self) -> bool:
        return self.matches("doc-steward")

    def is_catalog_contributor(self) -> bool:
        return self.matches("catalog-contributor")

    @staticmethod
    def _is_doc_steward_cwd() -> bool:
        return (Path.cwd() / "manifest.yaml").is_file()

    @staticmethod
    def is_deployer_cwd() -> bool:
        cwd = Path.cwd()
        return (cwd / "docker-compose.yml").is_file() and (
            cwd / "catalog.yaml"
        ).is_file()

    @staticmethod
    def is_catalog_contributor_cwd() -> bool:
        """Detect catalog-contributor role: catalog.yaml + .git + remote named jejune_catalog."""
        cwd = Path.cwd()
        if not (cwd / "catalog.yaml").is_file():
            return False
        if not (cwd / ".git").is_dir():
            return False
        try:
            url = subprocess.check_output(
                ["git", "remote", "get-url", "origin"],
                cwd=cwd,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            return (
                url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
                == CatalogConfig.REPO_NAME
            )
        except Exception:
            return False


Role.NONE = Role(name="", component_names=(), includes=(), section_title="")
