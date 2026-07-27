"""Role detection for jejune_cli.

Roles restrict `--help` output and `doctor` checks to what is relevant
for the active user persona. Role is inferred from the current directory;
the JEJUNE_ROLE env var overrides auto-detection.
"""

import os
from pathlib import Path

ROLES = ("doc-steward", "catalog-curator", "deployer")
_DISPLAY_ROLES = ("all",) + ROLES

_ROLE_COMPONENTS: dict[str, frozenset[str]] = {
    "doc-steward": frozenset(
        {"configuration", "neo4j", "llm", "llm-observability", "graph", "convert"}
    ),
    "catalog-curator": frozenset({"catalog", "test"}),
    # "deployment" = built-in; UI service names come from installed check/ plugins.
    "deployer": frozenset({"deployment", "docs-server", "kg-viewer", "md-browser"}),
}

_ROLE_INCLUDES: dict[str, tuple[str, ...]] = {
    "deployer": ("catalog-curator",),
}

_ROLE_REASON: dict[str, str] = {
    "all": "commands available regardless of role",
    "doc-steward": ".jejune/ directory detected",
    "catalog-curator": "full-catalog.yaml detected",
    "deployer": "docker-compose.yml detected",
}

ROLE_SECTION_TITLE: dict[str, str] = {
    "all": "All roles commands",
    "doc-steward": "Doc-steward commands",
    "catalog-curator": "Catalog-curator commands",
    "deployer": "Deployer commands",
}


def detect_role() -> tuple[str | None, str]:
    """Return (role, reason). Override with JEJUNE_ROLE env var."""
    override = os.environ.get("JEJUNE_ROLE")
    if override:
        if override in ROLES:
            return override, f"JEJUNE_ROLE={override}"
        return None, f"JEJUNE_ROLE={override!r} is not a known role (ignored)"
    cwd = Path.cwd()
    role_file = cwd / ".jejune" / "role"
    if role_file.is_file():
        role = role_file.read_text().strip()
        if role in ROLES:
            return role, ".jejune/role"
    if (cwd / "docker-compose.yml").exists():
        return "deployer", _ROLE_REASON["deployer"]
    if (cwd / ".jejune").is_dir():
        return "doc-steward", _ROLE_REASON["doc-steward"]
    if (cwd / "full-catalog.yaml").exists():
        return "catalog-curator", _ROLE_REASON["catalog-curator"]
    return None, "no role indicator found in current directory"


def role_components(role: str | None) -> frozenset[str] | None:
    """Component filter for the role, or None (show everything)."""
    if not role:
        return None
    own = _ROLE_COMPONENTS.get(role, frozenset())
    for parent in _ROLE_INCLUDES.get(role, ()):
        own = own | _ROLE_COMPONENTS.get(parent, frozenset())
    return own or None
