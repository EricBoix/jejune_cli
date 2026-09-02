"""Deployer role: configuration data and workspace initialisation."""

import click

CONFIG_GROUPS: dict[str, tuple[list[str], str]] = {}
COMPONENT_CONFIG_HINTS: dict[str, str] = {}


class _DeployerInit(click.Command):
    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        formatter.write_usage(
            ctx.command_path,
            "[OPTIONS] [DIR_NAME]",
            prefix="Usage [deployer]: ",
        )


@click.command("init", cls=_DeployerInit)
@click.argument("dir_name", required=False, metavar="DIR_NAME")
def init(dir_name: str | None) -> None:
    """Scaffold a new UI deployment directory inside the current directory.

    DIR_NAME defaults to the name of the current directory when omitted.
    """
    from pathlib import Path
    from .ui_deployment import ui_configure
    effective_name = dir_name or Path.cwd().name
    click.get_current_context().invoke(
        ui_configure, deployments_dir=".", name=effective_name
    )
    if dir_name and dir_name not in (".", str(Path.cwd())):
        click.echo(f"  cd {effective_name}")
