"""Catalog-curator role: configuration data and workspace initialisation."""

import click

CONFIG_GROUPS: dict[str, tuple[list[str], str]] = {}
COMPONENT_CONFIG_HINTS: dict[str, str] = {}


@click.command("init")
def init() -> None:
    """Initialize the catalog-curator workspace. (Not yet implemented.)"""
    click.echo(click.style("Catalog Curator init: not yet implemented.", fg="yellow"))
