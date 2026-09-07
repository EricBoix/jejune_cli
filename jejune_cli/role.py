"""Role dataclass and workspace-detection helpers for jejune_cli."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class Role:
    name: str
    components: frozenset[str]
    includes: tuple[str, ...]
    section_title: str
    detector: Callable[[], bool] | None = None
    description: str = ""
    is_abstract: bool = False

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
    def _is_deployer_cwd() -> bool:
        cwd = Path.cwd()
        return (cwd / "docker-compose.yml").is_file() and (cwd / "catalog.yaml").is_file()


NO_ROLE = Role(name="", components=frozenset(), includes=(), section_title="")

CONTRIBUTOR = Role(
    name="contributor",
    components=frozenset({"ecosystem", "network", "git-command", "git-server"}),
    includes=(),
    section_title="Contributor commands",
    description="base ecosystem role",
)

DOC_STEWARD = Role(
    name="doc-steward",
    components=frozenset(
        {
            "docker-command",
            "docker-hub-server",
            "pypi-server",
            "neo4j",
            "llm",
            "llm-observability",
            "graph",
            "convert",
            "manifest",
        }
    ),
    includes=("contributor",),
    section_title="Doc-steward commands",
    description="document authoring",
    detector=Role._is_doc_steward_cwd,
)

# "deployment" = built-in; UI service names come from installed check/ plugins.
DEPLOYER = Role(
    name="deployer",
    components=frozenset(
        {
            "docker-command",
            "uv-command",
            "extensions",
            "catalog",
            "deployment",
            "docs-server",
            "kg-viewer",
            "md-browser",
        }
    ),
    includes=("contributor",),
    section_title="Deployer commands",
    description="service deployment",
    detector=Role._is_deployer_cwd,
)

# Re-export so existing callers keep working without import changes.
from .role_registry import ROLE_REGISTRY  # noqa: E402, F401
