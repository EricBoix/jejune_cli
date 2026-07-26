from pathlib import Path

import click

from .configuration import print_config_hint, print_config_status


@click.group(short_help="Manage deployments")
def deployment():
    """Manage deployments — collections of active jejune_doc_* repositories (collection-level)."""


@deployment.command("check-config")
def check_config():
    """Show per-variable configuration detail for the deployment component."""
    from .configuration import print_config_check
    print_config_check("deployment")


@deployment.command("status-config")
def status_config():
    """Show deployment configuration status."""
    print_config_status("deployment")


@deployment.command("hint-config")
def hint_config():
    """Show the configuration hint for the deployment component."""
    print_config_hint("deployment")



@deployment.command("list")
@click.argument("deployments_dir", type=click.Path(exists=True))
def list_deployments(deployments_dir):
    """List deployments found in DEPLOYMENTS_DIR."""
    root = Path(deployments_dir)
    dirs = sorted(d for d in root.iterdir() if d.is_dir() and d.name.startswith("deploy_"))
    if not dirs:
        click.echo("No deployments found.")
        return
    for d in dirs:
        catalog = d / "catalog.yaml"
        status = "ok" if catalog.exists() else "missing catalog.yaml"
        click.echo(f"  {d.name}  [{status}]")


# UI deployment commands live in ui_deployment.py; imported here to stay in this group.
from .ui_deployment import ui_build, ui_configure, ui_list, ui_start, ui_stop  # noqa: E402

for _cmd in (ui_configure, ui_list, ui_build, ui_start, ui_stop):
    deployment.add_command(_cmd)
