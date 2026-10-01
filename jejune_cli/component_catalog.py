"""Catalog configuration component."""

from pathlib import Path
from typing import ClassVar

import yaml

from ._package_paths import CatalogConfig, TemplatePaths
from .click_catalog_helpers import (
    load_catalog_docs,
    validate_catalog_entry,
    iter_docs,
)
from .component_manifest import CompManifest
from .component_with_config import ConfComp


class CompCatalog(ConfComp):
    _TRIVIAL_CATALOG: ClassVar[Path] = TemplatePaths.CATALOG_TRIVIAL

    def __init__(self, ecosystem, role_registry, plugin_registry) -> None:
        super().__init__(name="catalog", dependencies=[ecosystem])
        self._ecosystem = ecosystem
        self._role_registry = role_registry
        self.repos = [
            (None, None)
        ]  # registers jejune_catalog as an ecosystem-managed repo
        plugin_registry.register_repo_name(self.name, CatalogConfig.REPO_NAME)

    def check(self) -> tuple[str, str]:
        active_role = self._role_registry.detect_role()
        if self._role_registry.role_inherits(active_role, "deployment-catalog"):
            cwd = Path.cwd()
            full_cat = self.full_catalog_path(cwd.parent) or Path()
            results = self.check_deployment(cwd, full_cat, local_only=True)
            failing = [item for item, ok, _ in results if not ok]
            return ("ok", "") if not failing else ("error", "; ".join(failing))

        root_dir, tmp_dir = self._ecosystem.resolve_dirs()
        tier, base = self._ecosystem.repo_status(
            CatalogConfig.REPO_NAME, root_dir, tmp_dir
        )
        if tier in ("root", "tmp"):
            path = Path(base) / CatalogConfig.FULL_CATALOG
            return (
                ("ok", "")
                if path.exists()
                else (
                    "error",
                    f"{CatalogConfig.FULL_CATALOG} not found under {base}",
                )
            )

        try:
            local = self._ecosystem.ensure_local(CatalogConfig.REPO_NAME)
            path = local / CatalogConfig.FULL_CATALOG
            return (
                ("ok", "")
                if path.exists()
                else (
                    "error",
                    f"{CatalogConfig.FULL_CATALOG} not found after clone",
                )
            )
        except Exception as exc:
            return "error", f"could not access {CatalogConfig.REPO_NAME}: {exc}"

    def check_deployment(
        self,
        deployment_path: Path,
        catalog_ref: Path,
        local_only: bool = False,
    ) -> list[tuple[str, bool, str]]:
        """Validate a deployment catalog; return (item, ok, message)."""
        results: list[tuple[str, bool, str]] = []

        catalog_file = deployment_path / "catalog.yaml"
        results.append(
            (
                "catalog.yaml",
                catalog_file.exists(),
                "ok" if catalog_file.exists() else "missing",
            )
        )

        if not catalog_file.exists():
            return results

        ref_docs: dict[str, dict] = {}
        if catalog_ref.is_file():
            for doc in yaml.safe_load(catalog_ref.read_text()).get("documents", []):
                if isinstance(doc, dict) and "name" in doc:
                    ref_docs[doc["name"]] = doc

        root_dir, tmp_dir = (
            self._ecosystem.resolve_dirs(deployment_path)
            if self._ecosystem is not None
            else (None, None)
        )

        for i, doc in enumerate(
            yaml.safe_load(catalog_file.read_text()).get("documents", [])
        ):
            schema_errors = validate_catalog_entry(doc, i)
            if schema_errors:
                label = doc.get("name") if isinstance(doc, dict) else None
                results.append(
                    (label or f"entry #{i}", False, "; ".join(schema_errors))
                )
                continue
            name = doc["name"]
            url = doc["url"].rstrip("/")
            issues: list[str] = []

            if name in ref_docs:
                ref_url = ref_docs[name]["url"].rstrip("/")
                if url != ref_url:
                    issues.append(
                        f"URL drift: deployment={url!r}, reference={ref_url!r}"
                    )
            elif ref_docs:
                issues.append("not found in reference catalog")

            label = "public" if doc.get("public") else "private"
            results.append(
                (
                    name,
                    not issues,
                    f"ok ({label})" if not issues else "; ".join(issues),
                )
            )

            if self._ecosystem is not None:
                tier, base = self._ecosystem.repo_status(name, root_dir, tmp_dir)
                if tier == "remote":
                    if local_only:
                        continue
                    try:
                        base = str(self._ecosystem.ensure_local(name))
                    except Exception:
                        results.append(
                            (f"{name}/manifest.yaml", False, "could not clone repo")
                        )
                        continue
                manifest_errors, _ = CompManifest(
                    Path(base)
                ).check_manifest_referenced_files()
                results.append(
                    (
                        f"{name}/manifest.yaml",
                        not manifest_errors,
                        "ok" if not manifest_errors else "; ".join(manifest_errors),
                    )
                )

        return results

    def full_catalog_path(self, deployments_dir: Path) -> Path | None:
        """Locate full-catalog.yaml via ecosystem resolution, with sibling-path fallback."""
        root_dir, tmp_dir = self._ecosystem.resolve_dirs(deployments_dir)
        tier, base = self._ecosystem.repo_status(
            CatalogConfig.REPO_NAME, root_dir, tmp_dir
        )
        if tier in ("root", "tmp"):
            path = Path(base) / CatalogConfig.FULL_CATALOG
            return path if path.exists() else None
        candidate = (
            deployments_dir.parent
            / CatalogConfig.REPO_NAME
            / CatalogConfig.FULL_CATALOG
        )
        return candidate if candidate.exists() else None

    def has_private_repos(self, catalog_path: Path) -> bool:
        data = yaml.safe_load(catalog_path.read_text()) or {}
        return any(not doc.get("public", True) for doc in data.get("documents", []))

    def trivial_catalog_content(self) -> str | None:
        return (
            self._TRIVIAL_CATALOG.read_text()
            if self._TRIVIAL_CATALOG.exists()
            else None
        )

    def install_catalog(
        self,
        catalog_file: str | None = None,
        root_dir: str | None = None,
        repo: str | None = None,
    ) -> int:
        """Clone missing catalog repos into .jejune/tmp/; return count ready."""
        docs = load_catalog_docs(catalog_file)
        if repo:
            docs = [d for d in docs if d["name"] == repo]
        eco_root, eco_tmp = self._ecosystem.resolve_dirs()
        root = Path(root_dir) if root_dir and Path(root_dir).is_dir() else eco_root
        return sum(1 for _ in iter_docs(docs, root, eco_tmp, self._ecosystem))

    def doc_repo_names(self, catalog_path: Path) -> list[str]:
        """Return the list of doc repo names declared in *catalog_path*."""
        data = yaml.safe_load(catalog_path.read_text()) or {}
        return [doc["name"] for doc in data.get("documents", []) if "name" in doc]
