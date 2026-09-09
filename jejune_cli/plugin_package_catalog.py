"""Catalog of plugin packages — install metadata and install-state queries."""
from __future__ import annotations

import importlib.metadata
import subprocess
import sys

import click


class plugin_package_catalog:
    """Tracks installable plugin packages and answers install-state queries.

    The *expected* set of plugins for a role is derived from ``plugin_deps``
    declared on active components.  ``_BUILTIN_REPOS`` is the authoritative
    mapping from plugin name to source repository — used by ``install_packages``
    to locate a package regardless of whether it is already installed.
    """

    _BUILTIN_REPOS: dict[str, str] = {
        "kg-viewer": "jejune_kg-graph_viewer",
    }

    def _expected_plugin_names(self, role: str | None) -> set[str]:
        """Collect plugin_deps from all components active for *role*."""
        if not role:
            return set()
        from .role_registry import ROLE_REGISTRY
        from .component_registry import REGISTRY as COMP_REGISTRY
        role_obj = ROLE_REGISTRY.get(role)
        if role_obj is None:
            return set()
        role_comps = ROLE_REGISTRY.role_components(role_obj) or frozenset()
        return {
            name
            for comp in COMP_REGISTRY
            if comp in role_comps
            for name in getattr(comp, "plugin_deps", [])
        }

    def expected_plugin_names(self, role: str | None = None) -> list[str]:
        """Return sorted list of plugin names expected for *role*."""
        if role is None:
            from .role_registry import ROLE_REGISTRY
            r = ROLE_REGISTRY.detect_role()
            role = r.name if r else None
        return sorted(self._expected_plugin_names(role))

    def packages_installed(self, role: str | None = None) -> bool:
        """Return True when all expected plugins for *role* are installed."""
        if role is None:
            from .role_registry import ROLE_REGISTRY
            r = ROLE_REGISTRY.detect_role()
            role = r.name if r else None
        expected = self._expected_plugin_names(role)
        installed = {
            ep.name
            for ep in importlib.metadata.entry_points(group="jejune.plugins")
        }
        return all(name in installed for name in expected)

    def install_packages(self, role: str | None = None) -> None:
        """Install all expected plugin packages for *role*."""
        if role is None:
            from .role_registry import ROLE_REGISTRY
            r = ROLE_REGISTRY.detect_role()
            role = r.name if r else None
        for name in self._expected_plugin_names(role):
            repo_name = self._BUILTIN_REPOS.get(name)
            if repo_name is None:
                click.echo(
                    f"  {name}: {click.style('install info unknown', fg='red')}"
                    " — add it to plugin_package_catalog._BUILTIN_REPOS"
                )
                continue
            self._install_package(repo_name, name)

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
