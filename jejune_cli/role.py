"""Role detection for jejune_cli.

Roles restrict `--help` output and `doctor` checks to what is relevant
for the active user persona. Role is inferred from the current directory;
the JEJUNE_ROLE env var overrides auto-detection.
"""

import os
from pathlib import Path

ROLES = ("doc-steward", "catalog-curator", "deployer")

_ROLE_COMPONENTS: dict[str, frozenset[str]] = {
    "doc-steward":     frozenset({"neo4j", "llm", "llm-observability", "graph", "convert"}),
    "catalog-curator": frozenset({"catalog"}),
    # "deployment" = built-in; UI service names come from installed check/ plugins.
    "deployer":        frozenset({"deployment", "docs-server", "kg-viewer", "md-browser"}),
}

_ROLE_REASON: dict[str, str] = {
    "doc-steward":     ".jejune/ directory detected",
    "catalog-curator": "full-catalog.yaml detected",
    "deployer":        "docker-compose.yml detected",
}


def detect_role() -> tuple[str | None, str]:
    """Return (role, reason). Override with JEJUNE_ROLE env var."""
    override = os.environ.get("JEJUNE_ROLE")
    if override:
        if override in ROLES:
            return override, f"JEJUNE_ROLE={override}"
        return None, f"JEJUNE_ROLE={override!r} is not a known role (ignored)"
    cwd = Path.cwd()
    if (cwd / "docker-compose.yml").exists():
        return "deployer", _ROLE_REASON["deployer"]
    if (cwd / ".jejune").is_dir():
        return "doc-steward", _ROLE_REASON["doc-steward"]
    if (cwd / "full-catalog.yaml").exists():
        return "catalog-curator", _ROLE_REASON["catalog-curator"]
    return None, "no role indicator found in current directory"


def role_components(role: str | None) -> frozenset[str] | None:
    """Component filter for the role, or None (show everything)."""
    return _ROLE_COMPONENTS.get(role) if role else None
