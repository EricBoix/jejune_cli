"""``jejune plugin-packages`` CLI group."""
import importlib.metadata

import click

from .app_context import AppContext


@click.group("plugin-packages", invoke_without_command=True,
             short_help="Manage plugin packages for the current role")
@click.pass_context
def plugin_packages_group(ctx: click.Context) -> None:
    """Install and inspect plugin packages for the current role."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(plugin_packages_status)


@plugin_packages_group.command("status")
@click.pass_context
def plugin_packages_status(ctx) -> None:
    """Show which plugin packages are installed for the current role."""
    app = ctx.find_object(AppContext)
    plugin_packages_comp = app.component_registry.get("plugin-packages")
    role = app.role_registry.detect_role()
    names = plugin_packages_comp.expected_plugin_names(role.name if role else None)
    if not names:
        click.echo("No plugin packages defined for the current role.")
        return
    installed = {ep.name for ep in importlib.metadata.entry_points(group="jejune.plugins")}
    for plugin_name in names:
        ok = plugin_name in installed
        label = click.style("installed", fg="green") if ok else click.style("missing", fg="red")
        click.echo(f"  {plugin_name}: {label}")


@plugin_packages_group.command("install")
@click.option("--no-cache", is_flag=True, default=False,
              help="Force fresh discovery of plugin repositories (ignore cached pyproject.toml reads).")
@click.pass_context
def plugin_packages_install(ctx, no_cache: bool) -> None:
    """Install plugin packages for the current role (local clone or git remote)."""
    app = ctx.find_object(AppContext)
    plugin_packages_comp = app.component_registry.get("plugin-packages")
    role = app.role_registry.detect_role()
    role_name = role.name if role else None
    if not plugin_packages_comp.expected_plugin_names(role_name):
        click.echo(click.style("No plugin packages defined for the current role.", fg="yellow"))
        return
    if not no_cache and plugin_packages_comp.packages_installed(role_name):
        click.echo("All plugin packages already installed.")
        return
    plugin_packages_comp.install_packages(role_name, no_cache=no_cache)
