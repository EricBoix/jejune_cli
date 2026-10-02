"""Deployer role: configuration data and workspace initialisation."""

import shutil
import sys
from pathlib import Path

import click

from ._package_paths import TemplatePaths
from .app_context import AppContext


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
    Creates catalog.yaml (seeded from the sibling jejune_docs_server repo's
    full-catalog.yaml when available), docker-compose.yml, and deployment.env.
    A .gitignore and secrets.env.template are added only when the catalog
    contains private repositories.
    """
    app = ctx.find_object(AppContext)
    effective_name = dir_name or Path.cwd().name
    deployments_dir = Path.cwd()
    deploy_dir = deployments_dir / effective_name

    if deploy_dir.exists():
        click.echo(f"Error: {deploy_dir} already exists.", err=True)
        sys.exit(1)

    try:
        deploy_dir.mkdir(parents=True)
    except OSError as exc:
        raise click.ClickException(str(exc)) from exc
    jejune_dir = deploy_dir / ".jejune"
    jejune_dir.mkdir()
    (jejune_dir / "origin").write_text(f"{deploy_dir}\n")
    shutil.copy(TemplatePaths.DEPLOYER_UI / "env-config", jejune_dir / "env-config")

    catalog_comp = app.component_registry.get("catalog")
    full_catalog = catalog_comp.full_catalog_path(deployments_dir)
    if full_catalog:
        shutil.copy(full_catalog, deploy_dir / "catalog.yaml")
        click.echo(f"Seeded catalog.yaml from {full_catalog}")
    else:
        template = catalog_comp.trivial_catalog_content()
        if template:
            (deploy_dir / "catalog.yaml").write_text(template)
        else:
            (deploy_dir / "catalog.yaml").write_text("documents: []\n")
        click.echo("Seeded catalog.yaml from built-in template — populate manually.")

    deployment_comp = app.component_registry.get("deployment")
    (deploy_dir / "docker-compose.yml").write_text(
        deployment_comp.generate_docker_compose(deploy_dir, TemplatePaths.DEPLOYER_UI)
    )
    shutil.copy(
        TemplatePaths.DEPLOYER_UI / "deployment.env", deploy_dir / "deployment.env"
    )

    if deployment_comp.has_private_repos(deploy_dir):
        (deploy_dir / ".gitignore").write_text("secrets.env\n")
        shutil.copy(
            TemplatePaths.DEPLOYER_UI / "secrets.env.template",
            deploy_dir / "secrets.env.template",
        )

    click.echo(f"Creating deployment in ./{deploy_dir.name}/ sub-directory")

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
