"""Built-in Role instances and their registration into RoleRegistry."""

import subprocess
from pathlib import Path

from ._package_paths import CatalogConfig
from .role import Role
from .role_registry import RoleRegistry


class RoleDetectors:
    """Workspace-detection predicates for the built-in roles."""

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


def wire_roles(registry: RoleRegistry) -> None:
    """Register all built-in roles into *registry*."""
    registry.register(
        Role(
            name="contributor",
            component_names=(
                "ecosystem",
                "network",
                "git-command",
                "git-server",
                "git-access",
            ),
            includes=(),
            section_title="Contributor commands",
            description="base ecosystem role",
            extra_commands=(
                "doctor",
                "configuration",
                "components",
                "role",
                "containers",
                "ecosystem",
                "next",
                "discover",
            ),
        )
    )
    registry.register(
        Role(
            name="doc-steward",
            component_names=(
                "docker-command",
                "docker-daemon",
                "docker-hub-server",
                "pypi-server",
                "neo4j",
                "oxigraph",
                "llm",
                "llm-observability",
                "graph",
                "neo4j-to-rdf-ttl",
                "convert",
                "manifest",
            ),
            includes=("contributor",),
            section_title="Doc-steward commands",
            description="document authoring",
            detector=RoleDetectors._is_doc_steward_cwd,
        )
    )
    registry.register(
        Role(
            name="deployment-catalog",
            component_names=("catalog",),
            includes=("contributor",),
            section_title="",
            is_abstract=True,
        )
    )
    registry.register(
        Role(
            name="catalog-contributor",
            component_names=(
                "docker-command",
                "docker-daemon",
                "oxigraph",
                "converters",
                "catalog",
            ),
            includes=("contributor", "deployment-catalog"),
            section_title="Catalog-contributor commands",
            description="collection catalog management",
            detector=RoleDetectors.is_catalog_contributor_cwd,
        )
    )
    registry.register(
        Role(
            name="deployer",
            component_names=(
                "docker-command",
                "docker-daemon",
                "docker-hub-server",
                "uv-command",
                "plugin-packages",
                "catalog",
                "oxigraph",
                "deployment",
                "docs-server",
                "kg-viewer",
                "md-browser",
            ),
            includes=("contributor", "deployment-catalog"),
            section_title="Deployer commands",
            description="service deployment",
            detector=RoleDetectors.is_deployer_cwd,
        )
    )
