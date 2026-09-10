"""The `jejune components list` command."""

import click

from .component_base import base_comp
from .component_ext import ext_comp
from .component_registry import REGISTRY as COMP_REGISTRY
from .click_theme import ClickTheme
from .role_registry import ROLE_REGISTRY


@click.command("list")
def components_list() -> None:
    """List all registered components and their availability status."""
    current_role_active_components: list[base_comp] = COMP_REGISTRY.sorted_active_set(
        ROLE_REGISTRY.current_role_components()
    )
    rows: list[tuple[str, str, str]] = []
    for comp in current_role_active_components:
        kind = "ext" if isinstance(comp, ext_comp) else "int"
        status, _ = comp.check()
        rows.append((comp.name, kind, status))

    _W_NAME = max(len("Component"), max(len(r[0]) for r in rows))
    _W_KIND = max(len("Type"), max(len(r[1]) for r in rows))

    click.echo(f"  {'Component':<{_W_NAME}}  {'Type':<{_W_KIND}}  Status")
    click.echo("  " + "─" * (_W_NAME + 2 + _W_KIND + 2 + len("Status")))
    for name, kind, status in rows:
        icon, fg = ClickTheme.status_icons.get(status, ("?", "white"))
        status_cell = click.style(icon, fg=fg)
        click.echo(f"  {name:<{_W_NAME}}  {kind:<{_W_KIND}}  {status_cell}")
