"""``jejune plugin-packages`` CLI group."""
import importlib.metadata

import click

from .plugin_package_catalog import PLUGIN_PACKAGE_CATALOG
from .role_registry import ROLE_REGISTRY


@click.group("plugin-packages", invoke_without_command=True,
             short_help="Manage plugin packages for the current role")
@click.pass_context
def plugin_packages_group(ctx: click.Context) -> None:
    """Install and inspect plugin packages for the current role."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(plugin_packages_status)


@plugin_packages_group.command("status")
def plugin_packages_status() -> None:
    """Show which plugin packages are installed for the current role."""
    role = ROLE_REGISTRY.detect_role()
    names = PLUGIN_PACKAGE_CATALOG.expected_plugin_names(role.name if role else None)
    if not names:
        click.echo("No plugin packages defined for the current role.")
        return
    installed = {ep.name for ep in importlib.metadata.entry_points(group="jejune.plugins")}
    for plugin_name in names:
        ok = plugin_name in installed
        label = click.style("installed", fg="green") if ok else click.style("missing", fg="red")
        click.echo(f"  {plugin_name}: {label}")


@plugin_packages_group.command("install")
def plugin_packages_install() -> None:
    """Install plugin packages for the current role (local clone or git remote)."""
    role = ROLE_REGISTRY.detect_role()
    role_name = role.name if role else None
    if not PLUGIN_PACKAGE_CATALOG.expected_plugin_names(role_name):
        click.echo(click.style("No plugin packages defined for the current role.", fg="yellow"))
        return
    if PLUGIN_PACKAGE_CATALOG.packages_installed(role_name):
        click.echo("All plugin packages already installed.")
        return
    PLUGIN_PACKAGE_CATALOG.install_packages(role_name)
