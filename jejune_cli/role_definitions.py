"""Built-in Role instances and their registration into ROLE_REGISTRY."""

from .role import Role
from .role_registry import ROLE_REGISTRY

_CONTRIBUTOR = Role(
    name="contributor",
    component_names=("ecosystem", "network", "git-command", "git-server"),
    includes=(),
    section_title="Contributor commands",
    description="base ecosystem role",
    extra_commands=("doctor", "configuration", "components", "role", "containers", "ecosystem", "next"),
)

_DOC_STEWARD = Role(
    name="doc-steward",
    component_names=(
        "docker-command", "docker-daemon", "docker-hub-server", "pypi-server",
        "neo4j", "llm", "llm-observability", "graph", "convert", "manifest",
    ),
    includes=("contributor",),
    section_title="Doc-steward commands",
    description="document authoring",
    detector=Role._is_doc_steward_cwd,
)

_DEPLOYMENT_CATALOG = Role(
    name="deployment-catalog",
    component_names=(),
    includes=(),
    section_title="",
    is_abstract=True,
)

_DEPLOYER = Role(
    name="deployer",
    component_names=(
        "docker-command", "docker-daemon", "uv-command", "plugin-packages",
        "catalog", "deployment", "docs-server", "kg-viewer", "md-browser",
    ),
    includes=("contributor", "deployment-catalog"),
    section_title="Deployer commands",
    description="service deployment",
    detector=Role.is_deployer_cwd,
)

ROLE_REGISTRY.register(_CONTRIBUTOR)
ROLE_REGISTRY.register(_DOC_STEWARD)
ROLE_REGISTRY.register(_DEPLOYMENT_CATALOG)
ROLE_REGISTRY.register(_DEPLOYER)
