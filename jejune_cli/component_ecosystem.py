"""Ecosystem component."""
import os
from pathlib import Path
from typing import Literal

from .configuration import configuration
from .configuration_entry import configuration_entry
from .component_with_config import conf_comp
# Cannot import COMP_REGISTRY because of circular dependency of imports between
# comp_ecosystem and ComponentRegistry
from .component_registry import ComponentRegistry
from .role_registry import ROLE_REGISTRY

RepoTier = Literal["root", "tmp", "remote"]


class comp_ecosystem(conf_comp):
    def __init__(self) -> None:
        git_server = ComponentRegistry().get("git-server")
        super().__init__(
            name="ecosystem",
            configuration=configuration(
                configuration_entry("JEJUNE_ROOT_DIR",
                    hint="edit .jejune/ecosystem-env-config and set JEJUNE_ROOT_DIR",
                    source_file=".jejune/ecosystem-env-config",
                    max_severity="warn")
            ),
        )
        self._git_server = git_server
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
        return self._git_server.remote_git_url(name, f"main:{subpath}" if subpath else None)

    def resolve_dirs(self, deploy_dir: Path | None = None) -> tuple[Path | None, Path | None]:
        from ._env import dot_jejune
        raw_root = os.environ.get("JEJUNE_ROOT_DIR")
        root_dir = Path(raw_root).resolve() if raw_root else None
        tmp = dot_jejune(deploy_dir) / "tmp"
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
                    results.append((name, "tmp", str(local), (local / "manifest.yaml").exists()))
        return results

    def ecosystem_needs_remote(self) -> bool:
        """Does the ecosystem still need to reach a remote git server?"""
        active = ROLE_REGISTRY.current_role_components()
        if active is None:
            return False
        root_dir, tmp_dir = self.resolve_dirs()
        from .plugin_registry import PLUGIN_REGISTRY
        return any(
            self.repo_status(pkg_name, root_dir, tmp_dir)[0] == "remote"
            for comp in active
            if getattr(comp, "repos", [])
            if (pkg_name := PLUGIN_REGISTRY.repo_name_for_plugin(comp.name)) is not None
        )

    def ensure_local(self, repo_name: str) -> Path:
        import subprocess
        import click
        root_dir, tmp_dir = self.resolve_dirs()
        tier, base = self.repo_status(repo_name, root_dir, tmp_dir)
        if tier in ("root", "tmp"):
            return Path(base)
        if tmp_dir is None:
            from ._env import dot_jejune
            tmp_dir = dot_jejune() / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
        dest = tmp_dir / repo_name
        if not dest.exists():
            git_url = self._git_server.remote_git_url(repo_name)
            click.echo(f"Cloning {repo_name} ...")
            subprocess.run(["git", "clone", "--depth", "1", git_url, str(dest)], check=True)
        return dest

    def check(self) -> tuple[str, str]:
        return "ok", ""


