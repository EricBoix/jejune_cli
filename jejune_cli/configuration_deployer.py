"""Deployer role: configuration data and workspace initialisation."""

import click

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
    from .next_steps import print_next_steps
    from .ui_deployment import ui_configure
    effective_name = dir_name or Path.cwd().name
    click.get_current_context().invoke(
        ui_configure, deployments_dir=".", name=effective_name
    )
    cd_hint = None
    if dir_name and dir_name not in (".", str(Path.cwd())):
        cd_hint = [f"First: cd {effective_name}"]
    print_next_steps(preamble=cd_hint)


@click.group("deployer", short_help="Deployer role workspace")
def deployer_group():
    """Initialise and inspect the deployer workspace."""


deployer_group._role_subgroup = True
deployer_group.add_command(init, "init")
