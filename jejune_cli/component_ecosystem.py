"""Ecosystem component."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import click

from ._package_paths import CatalogConfig
from .component_catalog_document import CatalogDocument
from .component_catalog_file import CatalogFile
from .configuration import Configuration
from .configuration_entry import ConfigurationEntry
from .component_with_config import ConfComp
from .dot_jejune import DotJejune

RepoTier = Literal["root", "tmp", "remote"]
UpdateStatus = Literal["cloned", "updated", "up-to-date", "skipped", "failed"]


@dataclass(frozen=True)
class UpdateOutcome:
    """What `ecosystem update` did (or could not do) for one repository."""

    name: str
    status: UpdateStatus
    message: str = ""


class CompEcosystem(ConfComp):
    def __init__(self, git_server, git_access, role_registry, plugin_registry) -> None:
        super().__init__(
            name="ecosystem",
            dependencies=[git_access],
            configuration=Configuration(
                ConfigurationEntry(
                    CatalogConfig.ROOT_DIR_ENV_VAR,
                    hint="edit .jejune/ecosystem-env-config and set JEJUNE_ROOT_DIR",
                    source_file=".jejune/ecosystem-env-config",
                    max_severity="warn",
                )
            ),
        )
        self._git_server = git_server
        self._git_access = git_access
        self._role_registry = role_registry
        self._plugin_registry = plugin_registry
        self.conditional_dependencies = [(self.ecosystem_needs_remote, git_server)]

    def repo_status(
        self,
        name: str,
        root_dir: Path | None,
        tmp_dir: Path | None,
    ) -> tuple[RepoTier, str]:
        if root_dir is not None and (root_dir / name).exists():
            return "root", str(root_dir / name)
        if tmp_dir is not None and (tmp_dir / name).exists():
            return "tmp", str(tmp_dir / name)
        return "remote", self._git_server.remote_repo_path(name)

    def resolve(
        self,
        name: str,
        root_dir: Path | None,
        tmp_dir: Path | None,
        subpath: str | None = None,
    ) -> str:
        tier, base = self.repo_status(name, root_dir, tmp_dir)
        if tier in ("root", "tmp"):
            return str(Path(base) / subpath) if subpath else base
        return self._git_server.remote_git_url(
            name, f"main:{subpath}" if subpath else None
        )

    def resolve_dirs(
        self, deploy_dir: Path | None = None
    ) -> tuple[Path | None, Path | None]:
        raw_root = os.environ.get(CatalogConfig.ROOT_DIR_ENV_VAR)
        root_dir = Path(raw_root).resolve() if raw_root else None
        tmp = DotJejune(deploy_dir) / "tmp"
        return root_dir, tmp if tmp.is_dir() else None

    def discover_doc_repos(
        self,
        root_dir: Path | None,
        tmp_dir: Path | None,
        remote_names: list[str] | None = None,
    ) -> list[tuple[str, RepoTier, str, bool]]:
        seen: set[str] = set()
        results: list[tuple[str, RepoTier, str, bool]] = []
        for tier, base in (("root", root_dir), ("tmp", tmp_dir)):
            if base is None:
                continue
            for p in sorted(base.glob("jejune_doc_*")):
                if p.is_dir() and p.name not in seen:
                    seen.add(p.name)
                    results.append((p.name, tier, str(p), (p / "manifest.yaml").exists()))  # type: ignore[arg-type]
        if remote_names:
            for name in remote_names:
                if name not in seen:
                    seen.add(name)
                    local = self.ensure_local(name)
                    results.append(
                        (name, "tmp", str(local), (local / "manifest.yaml").exists())
                    )
        return results

    def ecosystem_needs_remote(self) -> bool:
        """Does the ecosystem still need to reach a remote git server?"""
        active = self._role_registry.current_role_components()
        if active is None:
            return False
        root_dir, tmp_dir = self.resolve_dirs()
        return any(
            self.repo_status(pkg_name, root_dir, tmp_dir)[0] == "remote"
            for comp in active
            if getattr(comp, "repos", [])
            if (pkg_name := self._plugin_registry.repo_name_for_plugin(comp.name))
            is not None
        )

    def ensure_local(self, repo_name: str) -> Path:
        root_dir, tmp_dir = self.resolve_dirs()
        tier, base = self.repo_status(repo_name, root_dir, tmp_dir)
        if tier in ("root", "tmp"):
            return Path(base)
        # A repository of the current catalog is cloned from its own url, with its
        # own access key; any other one from the default git server.
        catalog_path = CatalogFile.resolve_path()
        document = (
            CatalogFile(catalog_path).document(repo_name)
            if catalog_path.is_file()
            else None
        )
        git_url = (
            document.url
            if document is not None
            else self._git_server.remote_git_url(repo_name)
        )
        click.echo(f"Cloning {repo_name} ...")
        return self.clone_into_tmp(
            repo_name, git_url, document.effective_token_file if document else None
        )

    def clone_into_tmp(
        self,
        name: str,
        repository_url: str,
        token_file: Path | str | None = None,
        deploy_dir: Path | None = None,
    ) -> Path:
        """Shallow-clone *repository_url* into .jejune/tmp/*name* (of *deploy_dir*,
        else of the current directory) and return that directory."""
        destination = DotJejune(deploy_dir).tmp_dir() / name
        self.clone_repository(repository_url, destination, token_file)
        return destination

    def clone_repository(
        self,
        repository_url: str,
        destination: Path,
        token_file: Path | str | None = None,
    ) -> None:
        """Shallow-clone *repository_url*, authenticated through git-access when
        needed."""
        completed = self._git_access.run_git(
            ["clone", "--depth", "1", repository_url, str(destination)],
            repository_url,
            token_file,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise click.ClickException(
                f"cannot clone {repository_url}: wrong url or no access "
                f"(see `jejune git-access check-availability`)\n"
                f"{completed.stderr.strip()}"
            )

    def repo_up_to_date(
        self, repo_path: Path, token_file: Path | str | None = None
    ) -> bool | None:
        """Compare local HEAD to the actual remote HEAD via ls-remote (network call).

        *token_file* is the access key of a private repository (see
        CatalogFile.token_files).

        Returns True when in sync, False when behind, None on any error.
        Uses ls-remote rather than @{upstream} so the result is always current,
        not cached from the last fetch.
        """
        try:
            local = self._git_access.head_sha(repo_path)
            # ls-remote output: "<SHA>\tHEAD"
            ls_output = self._git_access.ls_remote(
                self._git_access.origin_url(repo_path),
                token_file,
                "HEAD",
                check=True,
            ).stdout.strip()
            remote = ls_output.split("\t")[0]
            return local == remote
        except (subprocess.CalledProcessError, IndexError, ValueError):
            return None

    def update_tmp_repo(
        self, repo_path: Path, token_file: Path | str | None = None
    ) -> bool:
        """Fetch origin and reset to FETCH_HEAD. Returns True when HEAD changed."""
        head_before = self._git_access.head_sha(repo_path)
        self._git_access.run_git(
            ["-C", str(repo_path), "fetch", "origin"],
            self._git_access.origin_url(repo_path),
            token_file,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "reset", "--hard", "FETCH_HEAD"],
            check=True,
        )
        head_after = self._git_access.head_sha(repo_path)
        return head_before != head_after

    def update_all_tmp_repos(
        self, deploy_dir: Path | None = None, skip_names: set[str] | None = None
    ) -> list[tuple[str, bool]]:
        """Update every git repo in .jejune/tmp/ (but the *skip_names* ones).

        Returns [(name, was_updated), ...].
        """
        _, tmp_dir = self.resolve_dirs(deploy_dir)
        if tmp_dir is None:
            return []
        results: list[tuple[str, bool]] = []
        for repo_path in sorted(tmp_dir.iterdir()):
            if skip_names and repo_path.name in skip_names:
                continue
            if repo_path.is_dir() and (repo_path / ".git").exists():
                click.echo(f"Updating {repo_path.name} ...")
                was_updated = self.update_tmp_repo(repo_path)
                results.append((repo_path.name, was_updated))
        return results

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
        root_dir, tmp_dir = self.resolve_dirs(deploy_dir)
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
        tier, base = self.repo_status(entry.name, root_dir, tmp_dir)
        if tier == "root":
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
            if tier == "tmp":
                was_updated = self.update_tmp_repo(Path(base), token_file)
                return UpdateOutcome(
                    entry.name, "updated" if was_updated else "up-to-date"
                )
            self.clone_into_tmp(entry.name, entry.url, token_file, deploy_dir)
            return UpdateOutcome(entry.name, "cloned")
        except subprocess.CalledProcessError as exc:
            return UpdateOutcome(
                entry.name,
                "failed",
                f"git exited with status {exc.returncode}: check the `url` of the "
                f"entry ({entry.url}) and its access key "
                "(`jejune git-access check-config`)",
            )

    def check(self) -> tuple[str, str]:
        return "ok", ""
