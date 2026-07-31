"""Deployer CLI check-extension management — `jejune deployment extensions`."""

import subprocess
from pathlib import Path

import click

_DEPLOYER_CHECK_PACKAGES: list[tuple[str, str, str]] = [
    # (repo_name,               check_subpath, plugin_name)
    ("jejune_docs_server",      "check",       "docs-server"),
    ("jejune_kg-graph_viewer",  "check",       "kg-viewer"),
    ("jejune_markdown_browser", "check",       "md-browser"),
]

_PLUGIN_NAMES: frozenset[str] = frozenset(t[2] for t in _DEPLOYER_CHECK_PACKAGES)


def _extensions_installed() -> bool:
    from .plugin import _REGISTRY
    installed = {p.name for p in _REGISTRY}
    return _PLUGIN_NAMES.issubset(installed)


@click.group("extensions", invoke_without_command=True,
             short_help="Manage deployer CLI check extensions")
@click.pass_context
def deployer_extensions(ctx: click.Context) -> None:
    """Install and check the three deployer HTTP-probe extensions."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(extensions_status)


@deployer_extensions.command("status")
def extensions_status() -> None:
    """Show which check extensions are installed."""
    from .plugin import _REGISTRY
    installed = {p.name for p in _REGISTRY}
    for _, _, plugin_name in _DEPLOYER_CHECK_PACKAGES:
        ok = plugin_name in installed
        label = click.style("installed", fg="green") if ok else click.style("missing", fg="red")
        click.echo(f"  {plugin_name}: {label}")


def _do_extensions_install() -> None:
    """Install the three deployer check extensions.

    Uses a local editable install when the repo is available via JEJUNE_ROOT_DIR
    or .jejune/tmp; falls back to installing directly from the git remote.
    """
    from .ecosystem import REPO_ROOT_DIR, repo_status, resolve_dirs

    root_dir, tmp_dir = resolve_dirs()

    for repo_name, check_subpath, plugin_name in _DEPLOYER_CHECK_PACKAGES:
        tier, base = repo_status(repo_name, root_dir, tmp_dir)
        if tier == "remote":
            git_url = f"git+{REPO_ROOT_DIR}/{repo_name}.git#subdirectory={check_subpath}"
            cmd = ["uv", "pip", "install", git_url]
        else:
            cmd = ["uv", "pip", "install", "-e", str(Path(base) / check_subpath)]
        result = subprocess.run(cmd)
        label = (
            click.style("installed", fg="green")
            if result.returncode == 0
            else click.style("failed", fg="red")
        )
        click.echo(f"  {plugin_name}: {label}")


@deployer_extensions.command("install")
def extensions_install() -> None:
    """Install the three deployer check extensions (local clone or git remote)."""
    _do_extensions_install()
