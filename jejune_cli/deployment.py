import click


@click.group(short_help="Manage deployments")
def deployment():
    """Manage deployments — collections of active jejune_doc_* repositories (collection-level)."""


# Deployment commands live in ui_deployment.py; imported here to stay in this group.
from .ui_deployment import ui_configure, ui_list, up, down, build  # noqa: E402, F401

for _cmd in (ui_list, up, down, build):
    deployment.add_command(_cmd)
