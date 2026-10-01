"""Built-in Role instances and their registration into RoleRegistry."""

from .role import Role
from .role_registry import RoleRegistry


def wire_roles(registry: RoleRegistry) -> None:
    """Register all built-in roles into *registry*."""
    registry.register(
        Role(
            name="contributor",
            component_names=("ecosystem", "network", "git-command", "git-server"),
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
                "llm",
                "llm-observability",
                "graph",
                "convert",
                "manifest",
            ),
            includes=("contributor",),
            section_title="Doc-steward commands",
            description="document authoring",
            detector=Role._is_doc_steward_cwd,
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
            component_names=("catalog",),
            includes=("contributor",),
            section_title="Catalog-contributor commands",
            description="collection catalog management",
            detector=Role.is_catalog_contributor_cwd,
        )
    )
    registry.register(
        Role(
            name="deployer",
            component_names=(
                "docker-command",
                "docker-daemon",
                "uv-command",
                "plugin-packages",
                "catalog",
                "deployment",
                "docs-server",
                "kg-viewer",
                "md-browser",
            ),
            includes=("contributor", "deployment-catalog"),
            section_title="Deployer commands",
            description="service deployment",
            detector=Role.is_deployer_cwd,
        )
    )
