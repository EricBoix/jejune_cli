"""Operations on a collection of document repositories listed in a catalog:
loading, checking, syncing and installing them."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import click

from ._package_paths import CatalogConfig
from .component_catalog_document import CatalogDocument
from .component_catalog_file import CatalogFile
from .component_ecosystem import EcosystemDirectories
from .component_git_access import CompGitAccess
from .dot_jejune import DotJejune


@dataclass(frozen=True)
class CatalogSelection:
    """The (raw) documents of a catalog and where to look for their repositories."""

    documents: list[dict]
    directories: EcosystemDirectories


class CatalogCollection:
    """Checks and installs the document repositories of a catalog."""

    def __init__(self, ecosystem) -> None:
        self._ecosystem = ecosystem

    def select(
        self,
        catalog_file: str | None = None,
        repo: str | None = None,
        root_dir: str | None = None,
    ) -> CatalogSelection:
        """The documents of the catalog (only *repo* when given) and the
        directories where to look for them (*root_dir* replacing the ecosystem
        root when it is an existing directory)."""
        documents = self.load_documents(catalog_file)
        if repo:
            documents = [document for document in documents if document["name"] == repo]
            if not documents:
                raise click.ClickException(f"Repository '{repo}' not found in catalog.")
        return CatalogSelection(
            documents, self._ecosystem.resolve_dirs().with_root(root_dir)
        )

    def install(
        self,
        catalog_file: str | None = None,
        root_dir: str | None = None,
        repo: str | None = None,
    ) -> int:
        """Clone missing catalog repos into .jejune/tmp/; return count ready."""
        selection = self.select(catalog_file, repo, root_dir)
        return sum(
            1
            for _ in self.iter_documents(selection.documents, selection.directories)
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
            schema_errors = CatalogDocument.validate_mapping(doc, i)
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

    def iter_documents(self, docs, directories: EcosystemDirectories):
        """Yield (name, url, repo_dir) for each catalog entry.

        Resolution order: JEJUNE_ROOT_DIR → .jejune/tmp → clone into .jejune/tmp.
        """
        for doc in docs:
            name, url = doc["name"], doc["url"]
            location = self._ecosystem.locate(name, directories)
            if location.is_local:
                repo_dir = location.local_path
            else:
                repo_dir = DotJejune().tmp_dir() / name
                if not repo_dir.exists():
                    click.echo(f"Cloning {name} ...")
                    self._ecosystem.clone_into_tmp(name, url, doc.get("token_file"))
            yield name, url, repo_dir
