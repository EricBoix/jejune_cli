"""Deployer role: configuration data and workspace initialisation."""

import click

CONFIG_GROUPS: dict[str, tuple[list[str], str]] = {}
COMPONENT_CONFIG_HINTS: dict[str, str] = {}


@click.command("init")
@click.argument("name", required=False)
def init(name: str | None) -> None:
    """Scaffold a new UI deployment directory NAME in the current directory."""
    if not name:
        raise click.UsageError("NAME is required for the deployer role.")
    from .ui_deployment import ui_configure
    click.get_current_context().invoke(ui_configure, deployments_dir=".", name=name)
