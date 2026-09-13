"""Catalog configuration component."""
from pathlib import Path

import yaml

from .component_with_config import conf_comp as component
from .component_registry import ComponentRegistry


class comp_catalog(component):
    def __init__(self) -> None:
        super().__init__(name="catalog", dependencies=[ComponentRegistry().get("ecosystem")])

    def check(self) -> tuple[str, str]:
        from jejune_catalog._impl import _check_availability
        ok, msg = _check_availability()
        return ("ok", "") if ok else ("error", msg)

    def full_catalog_path(self, deployments_dir: Path) -> Path | None:
        """Locate full-catalog.yaml in the sibling jejune_catalog repo."""
        candidate = deployments_dir.parent / "jejune_catalog" / "full-catalog.yaml"
        return candidate if candidate.exists() else None

    def has_private_repos(self, catalog_path: Path) -> bool:
        data = yaml.safe_load(catalog_path.read_text()) or {}
        return any(not doc.get("public", True) for doc in data.get("documents", []))

    def trivial_catalog_content(self) -> str | None:
        try:
            from importlib.resources import files
            return (files("jejune_catalog") / "templates" / "trivial-catalog.yaml").read_text()
        except Exception:
            return None

    def doc_repo_names(self, catalog_path: Path) -> list[str]:
        """Return the list of doc repo names declared in *catalog_path*."""
        data = yaml.safe_load(catalog_path.read_text()) or {}
        return [doc["name"] for doc in data.get("documents", []) if "name" in doc]


