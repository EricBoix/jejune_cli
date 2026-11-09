"""Catalog configuration component."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

import click
import yaml

from ._package_paths import CatalogConfig, SchemaPaths, TemplatePaths
from .component_catalog_access_checker import CatalogAccessChecker
from .component_catalog_document import CatalogDocument
from .component_catalog_file import CatalogFile
from .component_git_access import CompGitAccess
from .component_manifest import CompManifest
from .component_with_config import ConfComp
from .dot_jejune import DotJejune


UpdateStatus = Literal["cloned", "updated", "up-to-date", "skipped", "failed"]


@dataclass(frozen=True)
class UpdateOutcome:
    """What `ecosystem update` did (or could not do) for one repository."""

    name: str
    status: UpdateStatus
    message: str = ""


class CompCatalog(ConfComp):
    _TRIVIAL_CATALOG: ClassVar[Path] = TemplatePaths.CATALOG_TRIVIAL

    def __init__(self, ecosystem, git_access, role_registry, plugin_registry) -> None:
        super().__init__(name="catalog", dependencies=[ecosystem])
        self._ecosystem = ecosystem
        self._git_access = git_access
        self._role_registry = role_registry
        self.repos = [
            (None, None)
        ]  # registers jejune_catalog as an ecosystem-managed repo
        plugin_registry.register_repo_name(self.name, CatalogConfig.REPO_NAME)

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
            full_cat = self.full_catalog_path(cwd.parent) or Path()
            results = self.check_deployment(cwd, full_cat, local_only=True)
            failing = [item for item, ok, _ in results if not ok]
            return ("ok", "") if not failing else ("error", "; ".join(failing))

        location = self._ecosystem.locate_in(CatalogConfig.REPO_NAME)
        if location.is_local:
            path = location.local_path / CatalogConfig.FULL_CATALOG
            return (
                ("ok", "")
                if path.exists()
                else (
                    "error",
                    f"{CatalogConfig.FULL_CATALOG} not found under "
                    f"{location.local_path}",
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
            for doc in CatalogFile(catalog_ref).raw_documents():
                if isinstance(doc, dict) and "name" in doc:
                    ref_docs[doc["name"]] = doc

        root_dir, tmp_dir = (
            self._ecosystem.resolve_dirs(deployment_path)
            if self._ecosystem is not None
            else (None, None)
        )

        for i, doc in enumerate(CatalogFile(catalog_file).raw_documents()):
            schema_errors = self.validate_entry(doc, i)
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
                location = self._ecosystem.locate(name, root_dir, tmp_dir)
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

    def full_catalog_path(self, deployments_dir: Path) -> Path | None:
        """Locate full-catalog.yaml via ecosystem resolution, with sibling-path fallback."""
        location = self._ecosystem.locate_in(CatalogConfig.REPO_NAME, deployments_dir)
        if location.is_local:
            path = location.local_path / CatalogConfig.FULL_CATALOG
            return path if path.exists() else None
        candidate = (
            deployments_dir.parent
            / CatalogConfig.REPO_NAME
            / CatalogConfig.FULL_CATALOG
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

    def install_catalog(
        self,
        catalog_file: str | None = None,
        root_dir: str | None = None,
        repo: str | None = None,
    ) -> int:
        """Clone missing catalog repos into .jejune/tmp/; return count ready."""
        docs = self.load_documents(catalog_file)
        if repo:
            docs = [d for d in docs if d["name"] == repo]
        eco_root, eco_tmp = self._ecosystem.resolve_dirs()
        root = Path(root_dir) if root_dir and Path(root_dir).is_dir() else eco_root
        return sum(1 for _ in self.iter_documents(docs, root, eco_tmp))

    def doc_repo_names(self, catalog_path: Path) -> list[str]:
        """Return the list of doc repo names declared in *catalog_path*."""
        return CatalogFile(catalog_path).names()

    def update_catalog_repos(
        self, catalog_path: Path, deploy_dir: Path | None = None
    ) -> list[UpdateOutcome]:
        """Clone (when missing) or update, in .jejune/tmp/, every entry of the catalog.

        A failing entry (malformed, unusable git-access configuration, git error)
        yields a `failed` outcome carrying the reason: the other entries are
        still processed.
        """
        try:
            raw_documents = CatalogFile(catalog_path).raw_documents()
        except ValueError as exc:
            return [UpdateOutcome(str(catalog_path), "failed", str(exc))]
        root_dir, tmp_dir = self._ecosystem.resolve_dirs(deploy_dir)
        outcomes: list[UpdateOutcome] = []
        for index, raw_document in enumerate(raw_documents, 1):
            document = CatalogDocument.from_mapping(raw_document)
            if document is None:
                outcomes.append(
                    UpdateOutcome(
                        f"entry #{index}",
                        "failed",
                        "catalog entry without a `name` or a `url`",
                    )
                )
                continue
            outcomes.append(
                self.update_catalog_entry(document, root_dir, tmp_dir, deploy_dir)
            )
        return outcomes

    def update_catalog_entry(
        self,
        entry: CatalogDocument,
        root_dir: Path | None,
        tmp_dir: Path | None,
        deploy_dir: Path | None = None,
    ) -> UpdateOutcome:
        location = self._ecosystem.locate(entry.name, root_dir, tmp_dir)
        if location.tier == "root":
            return UpdateOutcome(
                entry.name,
                "skipped",
                "found in JEJUNE_ROOT_DIR: update it with git there",
            )
        try:
            entry.resolve_credentials(self._git_access)
        except ValueError as exc:
            return UpdateOutcome(entry.name, "failed", f"git-access: {exc}")
        token_file = entry.effective_token_file
        try:
            if location.tier == "tmp":
                was_updated = self._ecosystem.update_tmp_repo(location.local_path, token_file)
                return UpdateOutcome(
                    entry.name, "updated" if was_updated else "up-to-date"
                )
            self._ecosystem.clone_into_tmp(entry.name, entry.url, token_file, deploy_dir)
            return UpdateOutcome(entry.name, "cloned")
        except subprocess.CalledProcessError as exc:
            return UpdateOutcome(
                entry.name,
                "failed",
                f"git exited with status {exc.returncode}: check the `url` of the "
                f"entry ({entry.url}) and its access key "
                "(`jejune git-access check-config`)",
            )

    @staticmethod
    def load_documents(catalog_file: str | None) -> list[dict]:
        """Load and return the documents list from a catalog YAML file."""
        catalog_path = CatalogFile.resolve_path(catalog_file)
        if not catalog_path.exists():
            raise click.ClickException(f"Catalog file not found: {catalog_path}")
        try:
            return CatalogFile(catalog_path).raw_documents()
        except ValueError as exc:
            raise click.ClickException(f"{catalog_path}: {exc}") from exc

    @staticmethod
    def config_status() -> tuple[str, str]:
        """Return (status, raw_msg) for catalog configuration."""
        val = os.environ.get(CatalogConfig.ROOT_DIR_ENV_VAR)
        if not val:
            return "warn", f"{CatalogConfig.ROOT_DIR_ENV_VAR} not configured"
        if CatalogConfig.PLACEHOLDER in val:
            return "warn", f"{CatalogConfig.ROOT_DIR_ENV_VAR} has placeholder value"
        return "ok", ""

    @staticmethod
    def validate_entry(doc: object, index: int) -> list[str]:
        """Validate one entry against the deployment catalog schema; return error strings."""
        if not isinstance(doc, dict):
            return [f"entry #{index}: not a mapping"]
        schema = yaml.safe_load(SchemaPaths.CATALOG.read_text())
        errors: list[str] = []
        _TYPE_MAP = {"string": str, "boolean": bool}
        for field, ftype in schema.get("required_fields", {}).items():
            if field not in doc:
                errors.append(f"required field '{field}' missing")
            elif not isinstance(doc[field], _TYPE_MAP.get(ftype, object)):
                errors.append(f"'{field}' must be a {ftype}")
        for field, ftype in schema.get("optional_fields", {}).items():
            if field in doc and not isinstance(doc[field], _TYPE_MAP.get(ftype, object)):
                errors.append(f"'{field}' must be a {ftype}")
        if errors:
            errors.append(f"see {SchemaPaths.CATALOG} for the expected format")
        return errors

    @staticmethod
    def git_is_private(url: str) -> tuple[bool | None, str]:
        """Probe a remote URL via git ls-remote; return (is_private, error_message).

        The probe is deliberately anonymous (no git-access credentials): it asks
        whether the remote refuses anonymous access.

        Returns (False, "") when the remote is reachable (public or authenticated).
        Returns (True, "") when git exits 128, which indicates the remote refused
        anonymous access (error code 128: repository not found or access denied).
        Returns (None, msg) for transient or unrecognized failures.
        """
        try:
            result = CompGitAccess.ls_remote_anonymous(
                ["--exit-code", "--heads", url], timeout=15
            )
        except FileNotFoundError:
            return None, "git not found"
        except subprocess.TimeoutExpired:
            return None, "git ls-remote timed out"
        if result.returncode == 0 or result.returncode == 2:
            # 0 = refs found; 2 = no refs (empty repo) — both mean reachable
            return False, ""
        if result.returncode == 128:
            return True, ""
        return None, f"git ls-remote exited {result.returncode}: {result.stderr.strip()}"

    def check_collection(self, catalog: Path, root_dir: Path | None) -> list[tuple[str, bool, str]]:
        """Check each catalog entry for visibility and local clone; return (name, ok, message)."""
        if not catalog.exists():
            return [("catalog.yaml", False, f"not found: {catalog}")]
        try:
            docs = CatalogFile(catalog).raw_documents()
        except ValueError as exc:
            return [("catalog.yaml", False, str(exc))]
        results: list[tuple[str, bool, str]] = []
        for i, doc in enumerate(docs):
            schema_errors = self.validate_entry(doc, i)
            if schema_errors:
                label = doc.get("name") if isinstance(doc, dict) else None
                results.append((label or f"entry #{i}", False, "; ".join(schema_errors)))
                continue
            name = doc["name"]
            url = doc["url"].rstrip("/")
            expected_public = doc.get("public", True)
            issues: list[str] = []

            if root_dir is None:
                issues.append("JEJUNE_ROOT_DIR not set")
            elif not (root_dir / name).is_dir():
                issues.append(f"not cloned under {root_dir}")

            is_private, err = self.git_is_private(url)
            if err:
                issues.append(err)
            else:
                actual_public = not is_private
                if actual_public != expected_public:
                    catalog_val = "public" if expected_public else "private"
                    remote_val = "public" if actual_public else "private"
                    issues.append(
                        f"visibility mismatch: catalog={catalog_val}, remote={remote_val}"
                    )

            results.append((name, not issues, "; ".join(issues) if issues else "ok"))
        return results

    def sync_collection(
        self,
        catalog: Path,
        root_dir: Path,
        do_add: bool,
    ) -> tuple[list[tuple[str, bool, str]], int]:
        """Scan JEJUNE_ROOT_DIR for jejune_doc_* repos and compare against catalog.

        Returns (results, n_added) where n_added is the count of repos appended to
        catalog when do_add is True.
        """
        existing = set(CatalogFile(catalog).names()) if catalog.exists() else set()

        results: list[tuple[str, bool, str]] = []
        to_add: list[tuple[str, str]] = []

        for repo_dir in sorted(root_dir.glob("jejune_doc_*")):
            if not repo_dir.is_dir():
                continue
            name = repo_dir.name

            if name in existing:
                results.append((name, True, "already in catalog"))
                continue

            origin_url = CompGitAccess.origin_url(repo_dir)
            if origin_url is None:
                results.append((name, False, "no git remote"))
                continue

            url = origin_url.removesuffix(".git")

            is_private, err = self.git_is_private(url)
            if err:
                results.append((name, False, err))
                continue
            elif is_private:
                results.append(
                    (name, True, "private — add manually to deployment catalog if needed")
                )
            else:
                results.append((name, False, "public repo missing from catalog"))
                to_add.append((name, url))

        n_added = 0
        if do_add and to_add and catalog.exists():
            with catalog.open("a") as fh:
                for name, url in to_add:
                    fh.write(f"  - name: {name}\n")
                    fh.write(f"    url: {url}\n")
                    fh.write(f"    public: true\n")
            n_added = len(to_add)

        return results, n_added

    def iter_documents(self, docs, root, eco_tmp):
        """Yield (name, url, repo_dir) for each catalog entry.

        Resolution order: JEJUNE_ROOT_DIR → .jejune/tmp → clone into .jejune/tmp.
        """
        for doc in docs:
            name, url = doc["name"], doc["url"]
            location = self._ecosystem.locate(name, root, eco_tmp)
            if location.is_local:
                repo_dir = location.local_path
            else:
                repo_dir = DotJejune().tmp_dir() / name
                if not repo_dir.exists():
                    click.echo(f"Cloning {name} ...")
                    self._ecosystem.clone_into_tmp(name, url, doc.get("token_file"))
            yield name, url, repo_dir
