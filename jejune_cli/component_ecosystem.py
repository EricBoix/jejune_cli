"""Ecosystem component."""

import os
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import click

from ._package_paths import CatalogConfig
from .component_catalog_file import CatalogFile
from .configuration import Configuration
from .configuration_entry import ConfigurationEntry
from .component_with_config import ConfComp
from .dot_jejune import DotJejune

RepoTier = Literal["root", "tmp", "remote"]


@dataclass(frozen=True)
class EcosystemDirectories:
    """The directories where repositories are looked for, in this order: the
    JEJUNE_ROOT_DIR one (`root_dir`), then the `.jejune/tmp` one (`tmp_dir`)."""

    root_dir: Path | None
    tmp_dir: Path | None

    def with_root(self, root_dir: Path | str | None) -> "EcosystemDirectories":
        """Same directories, but with *root_dir* as root when it is an existing
        directory."""
        if root_dir and Path(root_dir).is_dir():
            return replace(self, root_dir=Path(root_dir))
        return self


@dataclass(frozen=True)
class RepoLocation:
    """Where a repository is: a local directory (tier root or tmp), else only its
    remote (`remote_path`, as given by the git-server)."""

    tier: RepoTier
    local_path: Path | None = None
    remote_path: str | None = None

    @property
    def is_local(self) -> bool:
        return self.local_path is not None


@dataclass(frozen=True)
class RepositoryState:
    """What the ecosystem knows of a repository: where it is and, when it is local,
    whether the clone is up to date (`up_to_date`) or, when it is only remote,
    its url and whether that remote could be reached (`reachable`, None when the
    remote was not probed)."""

    name: str
    location: RepoLocation
    remote_url: str | None = None
    reachable: bool | None = None
    up_to_date: bool | None = None
    commit: str | None = None

    @property
    def is_available(self) -> bool:
        """The repository is cloned locally or its remote could be reached."""
        return self.location.is_local or self.reachable is True


class CompEcosystem(ConfComp):
    REMOTE_PROBE_TIMEOUT_SECONDS = 15
    SHORT_SHA_LENGTH = 7

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
        self._registered_repositories: dict[str, list[str]] = {}
        self.conditional_dependencies = [(self.ecosystem_needs_remote, git_server)]

    def register_repository(
        self, owner_component_name: str, repository_name: str
    ) -> None:
        """Register *repository_name* as a repository managed by the ecosystem on
        behalf of a component: `ecosystem status` lists it whenever that component
        is active in the current role (idempotent)."""
        owned = self._registered_repositories.setdefault(owner_component_name, [])
        if repository_name not in owned:
            owned.append(repository_name)

    def registered_repositories(self, component_names: list[str]) -> list[str]:
        """The repositories registered by the given components, sorted and without
        duplicates."""
        return sorted(
            {
                repository_name
                for component_name in component_names
                for repository_name in self._registered_repositories.get(
                    component_name, []
                )
            }
        )

    def repository_state(
        self,
        name: str,
        directories: EcosystemDirectories,
        probe_remote: bool = False,
    ) -> RepositoryState:
        """The state of repository *name*; the remote of a repository found nowhere
        locally is only probed (network) when *probe_remote*."""
        location = self.locate(name, directories)
        if location.is_local:
            return RepositoryState(
                name,
                location,
                up_to_date=self.repo_up_to_date(location.local_path),
                commit=self.short_head(location.local_path),
            )
        remote_url = self._git_server.remote_git_url(name)
        reachable = self.remote_reachable(remote_url) if probe_remote else None
        return RepositoryState(
            name,
            location,
            remote_url=remote_url,
            reachable=reachable,
            commit=self.remote_short_head(remote_url) if reachable else None,
        )

    def short_head(self, repo_path: Path) -> str | None:
        """The short commit SHA of HEAD in the clone *repo_path* (None on error)."""
        try:
            return self._git_access.head_sha(repo_path)[: self.SHORT_SHA_LENGTH]
        except subprocess.CalledProcessError:
            return None

    def remote_short_head(
        self, repository_url: str, token_file: Path | str | None = None
    ) -> str | None:
        """The short commit SHA of the remote HEAD (default branch) of
        *repository_url* via ls-remote (network call); None on any error."""
        try:
            # ls-remote output: "<SHA>\tHEAD"
            ls_output = self._git_access.ls_remote(
                repository_url, token_file, "HEAD", check=True
            ).stdout.strip()
        except subprocess.CalledProcessError:
            return None
        return ls_output.split("\t")[0][: self.SHORT_SHA_LENGTH] or None

    def remote_reachable(self, repository_url: str) -> bool:
        """Can *repository_url* be reached anonymously (public repositories)?"""
        try:
            completed = self._git_access.ls_remote_anonymous(
                ["--exit-code", "--heads", repository_url],
                timeout=self.REMOTE_PROBE_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        # 2: reachable, but no reference (empty repository)
        return completed.returncode in (0, 2)

    def unshallow(self, repo_path: Path) -> None:
        """Fetch the whole history of a shallow clone (nothing to do for a complete
        one): git derived values, e.g. a commit count, need it."""
        shallow = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--is-shallow-repository"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if shallow != "true":
            return
        try:
            self._git_access.run_git(
                ["-C", str(repo_path), "fetch", "--unshallow"],
                self._git_access.origin_url(repo_path),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            click.echo(
                click.style(
                    f"  cannot fetch the whole history of {repo_path.name}: "
                    f"{error.stderr.strip()}",
                    fg="yellow",
                ),
                err=True,
            )

    def locate(self, name: str, directories: EcosystemDirectories) -> RepoLocation:
        root_dir, tmp_dir = directories.root_dir, directories.tmp_dir
        if root_dir is not None and (root_dir / name).exists():
            return RepoLocation("root", local_path=root_dir / name)
        if tmp_dir is not None and (tmp_dir / name).exists():
            return RepoLocation("tmp", local_path=tmp_dir / name)
        return RepoLocation(
            "remote", remote_path=self._git_server.remote_repo_path(name)
        )

    def locate_in(self, name: str, deploy_dir: Path | None = None) -> RepoLocation:
        """Same as locate, within the directories resolve_dirs(*deploy_dir*) gives."""
        return self.locate(name, self.resolve_dirs(deploy_dir))

    def resolve(
        self,
        name: str,
        directories: EcosystemDirectories,
        subpath: str | None = None,
    ) -> str:
        location = self.locate(name, directories)
        if location.is_local:
            return str(
                location.local_path / subpath if subpath else location.local_path
            )
        return self._git_server.remote_git_url(
            name, f"main:{subpath}" if subpath else None
        )

    def resolve_dirs(self, deploy_dir: Path | None = None) -> EcosystemDirectories:
        raw_root = os.environ.get(CatalogConfig.ROOT_DIR_ENV_VAR)
        root_dir = Path(raw_root).resolve() if raw_root else None
        tmp = DotJejune(deploy_dir) / "tmp"
        return EcosystemDirectories(root_dir, tmp if tmp.is_dir() else None)

    def discover_doc_repos(
        self,
        directories: EcosystemDirectories,
        remote_names: list[str] | None = None,
    ) -> list[tuple[str, RepoTier, str, bool]]:
        seen: set[str] = set()
        results: list[tuple[str, RepoTier, str, bool]] = []
        for tier, base in (
            ("root", directories.root_dir),
            ("tmp", directories.tmp_dir),
        ):
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
        # The catalog-contributor role always fetches the documents of catalog.yaml
        if self._role_registry.role_is_catalog_contributor_family(
            self._role_registry.detect_role()
        ):
            return True
        active = self._role_registry.current_role_components()
        if active is None:
            return False
        directories = self.resolve_dirs()
        return any(
            not self.locate(pkg_name, directories).is_local
            for comp in active
            if getattr(comp, "repos", [])
            if (pkg_name := self._plugin_registry.repo_name_for_plugin(comp.name))
            is not None
        )

    def ensure_local(self, repo_name: str) -> Path:
        location = self.locate_in(repo_name)
        if location.is_local:
            return location.local_path
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
        tmp_dir = self.resolve_dirs(deploy_dir).tmp_dir
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

    def check(self) -> tuple[str, str]:
        return "ok", ""
