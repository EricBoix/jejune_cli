"""Shared extension-package registry for all roles."""
import importlib.metadata
import subprocess
import sys
from pathlib import Path

import click

_ROLE_PACKAGES: dict[str, list[tuple[str, str, str]]] = {
    # (repo_name, check_subpath, plugin_name)
    "deployer": [
        ("jejune_docs_server",      "check", "docs-server"),
        ("jejune_kg-graph_viewer",  "check", "kg-viewer"),
        ("jejune_markdown_browser", "check", "md-browser"),
    ],
    "doc-steward": [
        ("jejune_catalog", "check", "catalog"),
    ],
}


def _install_one(repo_name: str, check_subpath: str, plugin_name: str) -> None:
    from .component_registry import REGISTRY

    eco = REGISTRY.get("ecosystem")
    root_dir, tmp_dir = eco.resolve_dirs()
    tier, base = eco.repo_status(repo_name, root_dir, tmp_dir)
    if tier == "remote":
        git_url = REGISTRY.get("git-server").remote_pip_url(repo_name, check_subpath)
        cmd = ["uv", "pip", "install", "--python", sys.executable, git_url]
    else:
        cmd = ["uv", "pip", "install", "--python", sys.executable, "-e", str(Path(base) / check_subpath)]
    result = subprocess.run(cmd)
    label = (
        click.style("installed", fg="green")
        if result.returncode == 0
        else click.style("failed", fg="red")
    )
    click.echo(f"  {plugin_name}: {label}")


def _extensions_installed(role: str | None = None) -> bool:
    """Return True when all extensions for *role* (or the detected role) are installed."""
    if role is None:
        from .role import detect_role
        role, _ = detect_role()
    pkgs = _ROLE_PACKAGES.get(role, [])
    installed = {ep.name for ep in importlib.metadata.entry_points(group="jejune.plugins")}
    return all(p[2] in installed for p in pkgs)


def _do_extensions_install(role: str | None = None) -> None:
    """Install all extensions for *role* (or the detected role)."""
    if role is None:
        from .role import detect_role
        role, _ = detect_role()
    for repo_name, check_subpath, plugin_name in _ROLE_PACKAGES.get(role, []):
        _install_one(repo_name, check_subpath, plugin_name)
