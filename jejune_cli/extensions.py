"""Unified `jejune extensions` CLI group."""
import importlib.metadata

import click

from .extensions_registry import _ROLE_PACKAGES, _do_extensions_install, _extensions_installed


@click.group("extensions", invoke_without_command=True,
             short_help="Manage jejune CLI extensions for the current role")
@click.pass_context
def extensions_group(ctx: click.Context) -> None:
    """Install and inspect jejune CLI extensions for the current role."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(extensions_status)


@extensions_group.command("status")
def extensions_status() -> None:
    """Show which extensions are installed for the current role."""
    from .role import detect_role

    role, _ = detect_role()
    pkgs = _ROLE_PACKAGES.get(role, [])
    if not pkgs:
        click.echo("No extensions defined for the current role.")
        return
    installed = {ep.name for ep in importlib.metadata.entry_points(group="jejune.plugins")}
    for _, _, plugin_name in pkgs:
        ok = plugin_name in installed
        label = click.style("installed", fg="green") if ok else click.style("missing", fg="red")
        click.echo(f"  {plugin_name}: {label}")


@extensions_group.command("install")
def extensions_install() -> None:
    """Install extensions for the current role (local clone or git remote)."""
    from .role import detect_role

    role, _ = detect_role()
    if role not in _ROLE_PACKAGES:
        click.echo(click.style("No extensions defined for the current role.", fg="yellow"))
        return
    if _extensions_installed():
        click.echo("All extensions already installed.")
        return
    _do_extensions_install()
