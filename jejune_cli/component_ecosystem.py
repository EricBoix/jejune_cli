"""Ecosystem component."""
import os
from pathlib import Path
from typing import Literal

from .configuration import configuration
from .component_with_config import conf_comp as component
from .component_registry import ComponentRegistry

RepoTier = Literal["root", "tmp", "remote"]


class comp_ecosystem(component):
    def __init__(self) -> None:
        git_server = ComponentRegistry().get("git-server")
        super().__init__(
            name="ecosystem",
            configuration=configuration("edit .jejune/ecosystem-env-config and set JEJUNE_ROOT_DIR", env_vars=["JEJUNE_ROOT_DIR"], max_severity="warn"),
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
        return results

    def ecosystem_needs_remote(self) -> bool:
        from .role_registry import ROLE_REGISTRY
        role = ROLE_REGISTRY.detect_role()
        root_dir, tmp_dir = self.resolve_dirs()
        active = ROLE_REGISTRY.role_components(role)
        if active is None:
            return False
        from .plugin_package_catalog import PLUGIN_PACKAGE_CATALOG
        return any(
            self.repo_status(PLUGIN_PACKAGE_CATALOG.get(comp.name), root_dir, tmp_dir)[0] == "remote"
            for comp in ComponentRegistry()
            if comp in active
            if getattr(comp, "repos", [])
        )

    def check(self) -> tuple[str, str]:
        return "ok", ""


