"""Catalog configuration component."""

from pathlib import Path
from typing import ClassVar

from ._package_paths import CatalogConfig, TemplatePaths
from .component_catalog_access_checker import CatalogAccessChecker
from .component_catalog_collection import CatalogCollection
from .component_catalog_document import CatalogDocument
from .component_catalog_file import CatalogFile
from .component_catalog_updater import CatalogUpdater
from .component_manifest import CompManifest
from .component_with_config import ConfComp


class CompCatalog(ConfComp):
    _TRIVIAL_CATALOG: ClassVar[Path] = TemplatePaths.CATALOG_TRIVIAL

    def __init__(self, ecosystem, git_access, role_registry, plugin_registry) -> None:
        super().__init__(name="catalog", dependencies=[ecosystem])
        self._ecosystem = ecosystem
        self._git_access = git_access
        self._role_registry = role_registry
        self.updater = CatalogUpdater(ecosystem, git_access)
        self.collection = CatalogCollection(ecosystem)
        plugin_registry.register_repo_name(self.name, CatalogConfig.REPO_NAME)

    @property
    def repos(self) -> list[tuple[None, None]]:
        # registers jejune_catalog as an ecosystem-managed repo, except for the
        # catalog-contributor role where jejune_catalog is the current directory
        if self._role_registry.role_is_catalog_contributor_family(
            self._role_registry.detect_role()
        ):
            return []
        return [(None, None)]

    def check_access(self, catalog_path: Path) -> tuple[str, str]:
        """The entries of *catalog_path* must have their access keys (own
        `token_file` or the environment): local checks only."""
        for status, subject, message in CatalogAccessChecker(
            self._git_access, catalog_path
        ).run():
            if status == "error":
                return status, f"{subject}: {message}"
        return "ok", ""

    def check(self) -> tuple[str, str]:
        catalog_path = CatalogFile.resolve_path()
        if catalog_path.is_file():
            access_status, access_message = self.check_access(catalog_path)
            if access_status != "ok":
                return access_status, access_message
        active_role = self._role_registry.detect_role()
        if self._role_registry.role_is_deployment_catalog_family(active_role):
            cwd = Path.cwd()
            reference_catalog = self.reference_catalog_path(cwd.parent) or Path()
            results = self.check_deployment(cwd, reference_catalog, local_only=True)
            failing = [item for item, ok, _ in results if not ok]
            return ("ok", "") if not failing else ("error", "; ".join(failing))

        location = self._ecosystem.locate_in(CatalogConfig.REPO_NAME)
        if location.is_local:
            path = location.local_path / CatalogConfig.REFERENCE_CATALOG
            return (
                ("ok", "")
                if path.exists()
                else (
                    "error",
                    f"{CatalogConfig.REFERENCE_CATALOG} not found under "
                    f"{location.local_path}",
                )
            )

        try:
            local = self._ecosystem.ensure_local(CatalogConfig.REPO_NAME)
            path = local / CatalogConfig.REFERENCE_CATALOG
            return (
                ("ok", "")
                if path.exists()
                else (
                    "error",
                    f"{CatalogConfig.REFERENCE_CATALOG} not found after clone",
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
            for doc in CatalogFile(catalog_ref).raw_documents():
                if isinstance(doc, dict) and "name" in doc:
                    ref_docs[doc["name"]] = doc

        directories = (
            self._ecosystem.resolve_dirs(deployment_path)
            if self._ecosystem is not None
            else None
        )

        for i, doc in enumerate(CatalogFile(catalog_file).raw_documents()):
            schema_errors = CatalogDocument.validate_mapping(doc, i)
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

            label = "public" if doc.get("public", True) else "private"
            results.append(
                (
                    name,
                    not issues,
                    f"ok ({label})" if not issues else "; ".join(issues),
                )
            )

            if self._ecosystem is not None:
                location = self._ecosystem.locate(name, directories)
                if location.is_local:
                    manifest_dir = location.local_path
                else:
                    if local_only:
                        continue
                    try:
                        manifest_dir = self._ecosystem.ensure_local(name)
                    except Exception as exc:
                        results.append(
                            (
                                f"{name}/manifest.yaml",
                                False,
                                f"could not clone repo: {exc}",
                            )
                        )
                        continue
                manifest_errors, _ = CompManifest(
                    manifest_dir
                ).check_manifest_referenced_files()
                results.append(
                    (
                        f"{name}/manifest.yaml",
                        not manifest_errors,
                        "ok" if not manifest_errors else "; ".join(manifest_errors),
                    )
                )

        return results

    def reference_catalog_path(self, deployments_dir: Path) -> Path | None:
        """Locate the reference catalog (jejune_catalog/catalog.yaml) via ecosystem resolution, with sibling-path fallback."""
        location = self._ecosystem.locate_in(CatalogConfig.REPO_NAME, deployments_dir)
        if location.is_local:
            path = location.local_path / CatalogConfig.REFERENCE_CATALOG
            return path if path.exists() else None
        candidate = (
            deployments_dir.parent
            / CatalogConfig.REPO_NAME
            / CatalogConfig.REFERENCE_CATALOG
        )
        return candidate if candidate.exists() else None

    def repository_urls(self) -> list[str]:
        """Return the URLs of the entries of the catalog of the current directory
        (JEJUNE_CATALOG when set); empty when there is no such catalog."""
        catalog_path = CatalogFile.resolve_path()
        if not catalog_path.is_file():
            return []
        return [document.url for document in CatalogFile(catalog_path).documents()]

    def private_repositories(self, catalog_path: Path) -> list[tuple[str, str | None]]:
        """Return (url, token_file) of each private entry of *catalog_path*."""
        return [
            (document.url, document.token_file)
            for document in CatalogFile(catalog_path).private_documents()
        ]

    def has_private_repos(self, catalog_path: Path) -> bool:
        return bool(CatalogFile(catalog_path).private_documents())

    def trivial_catalog_content(self) -> str | None:
        return (
            self._TRIVIAL_CATALOG.read_text()
            if self._TRIVIAL_CATALOG.exists()
            else None
        )
