"""Deployer role: configuration data and workspace initialisation."""

from pathlib import Path

import click

from .app_context import AppContext
from .click_comp_deployment import ui_configure

class _DeployerInit(click.Command):
    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        formatter.write_usage(
            ctx.command_path,
            "[OPTIONS] [DIR_NAME]",
            prefix="Usage [deployer]: ",
        )


@click.command("init", cls=_DeployerInit)
@click.argument("dir_name", required=False, metavar="DIR_NAME")
@click.pass_context
def init(ctx, dir_name: str | None) -> None:
    """Scaffold a new UI deployment directory inside the current directory.

    DIR_NAME defaults to the name of the current directory when omitted.
    """
    app = ctx.find_object(AppContext)
    effective_name = dir_name or Path.cwd().name
    ctx.invoke(ui_configure, deployments_dir=".", name=effective_name)
    plugin_packages_comp = app.component_registry.get("plugin-packages")
    if not plugin_packages_comp.packages_installed(role="deployer"):
        click.echo("\nInstalling deployer plugin packages...")
        plugin_packages_comp.install_packages(role="deployer")
    cd_hint = None
    if dir_name and dir_name not in (".", str(Path.cwd())):
        cd_hint = [f"First: cd {effective_name}"]
    app.heuristic_step_registry.print_next_steps(preamble=cd_hint)


@click.group("deployer", short_help="Deployer role workspace")
def deployer_group():
    """Initialise and inspect the deployer workspace."""


deployer_group._role_subgroup = True
deployer_group.add_command(init, "init")
