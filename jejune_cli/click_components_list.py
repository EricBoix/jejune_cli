"""The `jejune components list` command."""

import click

from jejune_cli.core.app_context import AppContext
from jejune_cli.core.component_base import BaseComp
from .component_ext import ExtComp
from .click_theme import ClickTheme


@click.command("list")
@click.pass_context
def components_list(ctx) -> None:
    """List all registered components and their availability status."""
    app = ctx.find_object(AppContext)
    current_role_active_components: list[BaseComp] = (
        app.component_registry.sorted_active_set(
            app.role_registry.current_role_components()
        )
    )
    rows: list[tuple[str, str, str]] = []
    for comp in current_role_active_components:
        kind = "ext" if isinstance(comp, ExtComp) else "int"
        status, _ = comp.check()
        rows.append((comp.name, kind, status))

    _W_NAME = max(len("Component"), max(len(row[0]) for row in rows))
    _W_KIND = max(len("Type"), max(len(row[1]) for row in rows))

    click.echo(f"  {'Component':<{_W_NAME}}  {'Type':<{_W_KIND}}  Status")
    click.echo("  " + "─" * (_W_NAME + 2 + _W_KIND + 2 + len("Status")))
    for name, kind, status in rows:
        icon, fg = ClickTheme.status_icons.get(status, ("?", "white"))
        status_cell = click.style(icon, fg=fg)
        click.echo(f"  {name:<{_W_NAME}}  {kind:<{_W_KIND}}  {status_cell}")
