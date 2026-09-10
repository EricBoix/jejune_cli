"""The `jejune components` command group."""

import click

from .click_components_list import components_list
from .click_components_tree import components_tree


@click.group(short_help="Inspect registered components")
def components():
    """Inspect jejune components."""


components.add_command(components_list)
components.add_command(components_tree)
