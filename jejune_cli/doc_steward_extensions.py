"""Doc-steward CLI extension management — catalog-contributor."""

import importlib.metadata
import subprocess
import sys
from pathlib import Path

import click

from .next_steps import register_precondition

_CATALOG_PACKAGE = ("jejune_catalog", "check", "catalog")
# (repo_name, check_subpath, plugin_name)

_PLUGIN_NAME: str = _CATALOG_PACKAGE[2]


def _extension_installed() -> bool:
    """Return True when the catalog-contributor extension is installed.

    Reads importlib.metadata directly so it reflects packages installed
    mid-process (e.g. by _do_extension_install), not just the startup snapshot.
    """
    installed = {ep.name for ep in importlib.metadata.entry_points(group="jejune.plugins")}
    return _PLUGIN_NAME in installed


register_precondition("catalog-contributor extension installed", _extension_installed)


def _do_extension_install() -> None:
    """Install the catalog-contributor extension.

    Uses a local editable install when the repo is available via JEJUNE_ROOT_DIR
    or .jejune/tmp; falls back to installing directly from the git remote.
    """
    from .ecosystem import repo_status, resolve_dirs
    from .component_git_server import remote_pip_url

    root_dir, tmp_dir = resolve_dirs()
    repo_name, check_subpath, plugin_name = _CATALOG_PACKAGE
    tier, base = repo_status(repo_name, root_dir, tmp_dir)
    if tier == "remote":
        git_url = remote_pip_url(repo_name, check_subpath)
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


@click.group("extensions", invoke_without_command=True,
             short_help="Manage doc-steward CLI extensions")
@click.pass_context
def doc_steward_extensions(ctx: click.Context) -> None:
    """Install and check the catalog-contributor extension."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(extensions_status)


@doc_steward_extensions.command("status")
def extensions_status() -> None:
    """Show whether the catalog-contributor extension is installed."""
    ok = _extension_installed()
    label = click.style("installed", fg="green") if ok else click.style("missing", fg="red")
    click.echo(f"  {_PLUGIN_NAME}: {label}")


@doc_steward_extensions.command("install")
def extensions_install() -> None:
    """Install the catalog-contributor extension (local clone or git remote)."""
    _do_extension_install()
