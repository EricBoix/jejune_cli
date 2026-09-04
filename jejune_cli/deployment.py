import click


@click.group(short_help="Manage deployments")
def deployment():
    """Manage deployments — collections of active jejune_doc_* repositories (collection-level)."""


# Deployment commands live in ui_deployment.py; imported here to stay in this group.
from .ui_deployment import ui_configure, ui_list, up, down, build, status  # noqa: E402, F401


@deployment.command("install")
def deployment_install() -> None:
    """Install all deployment components: catalog repos and check extensions."""
    from .extensions_registry import _do_extensions_install
    try:
        from jejune_catalog._commands import _do_catalog_install
        click.echo("Installing catalog repositories...")
        _do_catalog_install()
    except ImportError:
        click.echo(click.style(
            "  catalog plugin not installed — skipping", fg="yellow"
        ))
    click.echo("Installing deployer extensions...")
    _do_extensions_install()


for _cmd in (ui_list, up, down, build, status, deployment_install):
    deployment.add_command(_cmd)
