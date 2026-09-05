"""Ecosystem component."""
import os
from pathlib import Path

from .configuration import configuration
from .component_internal import component
from .role import RepoTier


class comp_ecosystem(component):
    def __init__(self) -> None:
        git_server = type(self).registry.get("git-server")
        super().__init__(
            name="ecosystem",
            dependencies=[git_server],
            configuration=configuration("edit .jejune/ecosystem-env-config and set JEJUNE_ROOT_DIR", env_vars=["JEJUNE_ROOT_DIR"], max_severity="warn"),
        )
        self._git_server = git_server
        type(self).registry.add(self)

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
        from .role import detect_role, repos_for_role
        role, _ = detect_role()
        root_dir, tmp_dir = self.resolve_dirs()
        return any(
            self.repo_status(name, root_dir, tmp_dir)[0] == "remote"
            for name, _, _ in repos_for_role(role)
        )

    def check(self) -> tuple[str, str]:
        return "ok", ""


comp_ecosystem()
