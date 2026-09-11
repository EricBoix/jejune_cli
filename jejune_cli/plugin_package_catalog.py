"""Catalog of plugin packages — install metadata and install-state queries."""
from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from pathlib import Path

import click

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-reuse-import]


class plugin_package_catalog:
    """Tracks installable plugin packages and answers install-state queries.

    ``plugin_deps`` on active components holds repository names (e.g.
    ``"jejune_docs_server"``); ``_discover`` clones them and reads their
    ``pyproject.toml`` to derive the entry-point name.  ``_discover`` reads each repo's
    ``pyproject.toml`` at runtime to derive the plugin name — the first key of
    ``[project.entry-points."jejune.plugins"]``.
    """

    def __init__(self) -> None:
        self._discovery_cache: dict[str, str] | None = None

    def _discover(self, repo_names: list[str], no_cache: bool = False) -> dict[str, str]:
        """Return {repo_name: plugin_name} from each repo's pyproject.toml.

        Clones repos not available locally, reporting each clone to the user.
        Result is cached per process; pass *no_cache=True* to force a re-read.
        """
        if no_cache:
            self._discovery_cache = None
        if self._discovery_cache is not None:
            return self._discovery_cache
        from .component_registry import REGISTRY as COMP_REGISTRY
        eco = COMP_REGISTRY.get("ecosystem")
        root_dir, tmp_dir = eco.resolve_dirs()
        result: dict[str, str] = {}
        seen: set[str] = set()
        for repo_name in repo_names:
            if repo_name in seen:
                continue
            seen.add(repo_name)
            tier, base = eco.repo_status(repo_name, root_dir, tmp_dir)
            if tier == "remote":
                if tmp_dir is None:
                    from ._env import dot_jejune
                    tmp_dir = dot_jejune() / "tmp"
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                dest = tmp_dir / repo_name
                if not dest.exists():
                    git_url = COMP_REGISTRY.get("git-server").remote_git_url(repo_name)
                    click.echo(f"Cloning {repo_name} ...")
                    subprocess.run(
                        ["git", "clone", "--depth", "1", git_url, str(dest)],
                        check=True,
                    )
                pyproject_path = dest / "pyproject.toml"
            else:
                pyproject_path = Path(base) / "pyproject.toml"
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            eps = (
                data.get("project", {})
                .get("entry-points", {})
                .get("jejune.plugins", {})
            )
            if not eps:
                click.echo(
                    f"  {repo_name}: {click.style('no jejune.plugins entry-point in pyproject.toml', fg='red')}"
                )
                continue
            result[repo_name] = next(iter(eps))
        self._discovery_cache = result
        return result

    def repo_name_for(self, plugin_name: str) -> str | None:
        """Return the repo name for *plugin_name*, or None if not yet discovered."""
        if self._discovery_cache is None:
            return None
        for repo, name in self._discovery_cache.items():
            if name == plugin_name:
                return repo
        return None

    def _all_repo_names(self, role: str | None) -> list[str]:
        """Collect plugin_deps (repo names) from all components active for *role*."""
        if not role:
            return []
        from .role_registry import ROLE_REGISTRY
        from .component_registry import REGISTRY as COMP_REGISTRY
        role_obj = ROLE_REGISTRY.get(role)
        if role_obj is None:
            return []
        role_comps = ROLE_REGISTRY.role_components(role_obj) or frozenset()
        return [
            name
            for comp in COMP_REGISTRY
            if comp in role_comps
            for name in getattr(comp, "plugin_deps", [])
        ]

    def _expected_plugin_names(self, role: str | None) -> set[str]:
        repo_names = self._all_repo_names(role)
        if not repo_names:
            return set()
        return set(self._discover(repo_names).values())

    def expected_plugin_names(self, role: str | None = None) -> list[str]:
        """Return sorted list of plugin names expected for *role*."""
        if role is None:
            from .role_registry import ROLE_REGISTRY
            r = ROLE_REGISTRY.detect_role()
            role = r.name if r else None
        return sorted(self._expected_plugin_names(role))

    def packages_installed(self, role: str | None = None) -> bool:
        """Return True when all expected plugin packages for *role* are installed."""
        if role is None:
            from .role_registry import ROLE_REGISTRY
            r = ROLE_REGISTRY.detect_role()
            role = r.name if r else None
        expected = self._expected_plugin_names(role)
        if not expected:
            return True
        installed = {ep.name for ep in importlib.metadata.entry_points(group="jejune.plugins")}
        return expected.issubset(installed)

    def install_packages(self, role: str | None = None, no_cache: bool = False) -> None:
        """Install all expected plugin packages for *role*."""
        if role is None:
            from .role_registry import ROLE_REGISTRY
            r = ROLE_REGISTRY.detect_role()
            role = r.name if r else None
        repo_names = self._all_repo_names(role)
        if not repo_names:
            return
        discovered = self._discover(repo_names, no_cache=no_cache)
        for repo_name in repo_names:
            self._install_package(repo_name, discovered.get(repo_name, repo_name))

    def _install_package(self, repo_name: str, plugin_name: str) -> None:
        from .component_registry import REGISTRY as COMP_REGISTRY
        eco = COMP_REGISTRY.get("ecosystem")
        root_dir, tmp_dir = eco.resolve_dirs()
        tier, base = eco.repo_status(repo_name, root_dir, tmp_dir)
        if tier == "remote":
            git_url = COMP_REGISTRY.get("git-server").remote_pip_url(repo_name)
            cmd = ["uv", "pip", "install", "--python", sys.executable, git_url]
        else:
            cmd = ["uv", "pip", "install", "--python", sys.executable, "-e", base]
        result = subprocess.run(cmd)
        label = (
            click.style("installed", fg="green")
            if result.returncode == 0
            else click.style("failed", fg="red")
        )
        click.echo(f"  {plugin_name}: {label}")


PLUGIN_PACKAGE_CATALOG = plugin_package_catalog()
