import click

from .component_registry import REGISTRY as COMP_REGISTRY

_META_URL = "viewer_url"


class _ViewGroup(click.Group):
    """Group that treats an unrecognized first argument as a file URL rather
    than raising 'No such command'."""

    def invoke(self, ctx: click.Context) -> object:
        args = [*ctx._protected_args, *ctx.args]
        if args and self.get_command(ctx, args[0]) is None:
            ctx._protected_args = []
            ctx.args = []
            ctx.meta[_META_URL] = args[0]
        return super().invoke(ctx)


@click.group(
    "view",
    cls=_ViewGroup,
    invoke_without_command=True,
    short_help="Visualize a turtle file in the browser",
)
@click.option("--new-server", is_flag=True, help="Start a new viewer container")
@click.option("--list", "list_viewers", is_flag=True, help="List viewer containers")
@click.pass_context
def view(ctx, new_server, list_viewers):
    """Visualize a turtle RDF file (file:// URL) in the browser.

    \b
    jejune graph view path/to/file.ttl
    jejune graph view /path/to/file.ttl
    jejune graph view file:///path/to/file.ttl
    jejune graph view --new-server path/to/file.ttl
    jejune graph view --list
    jejune graph view stop [ID|all]

    Reuses the last running container unless --new-server is given.
    Set JEJUNE_BROWSER to override the browser command.
    Set KG_GRAPH_VIEWER_CONTEXT to a local clone of jejune_kg-graph_viewer.
    """
    kg_viewer = COMP_REGISTRY.get("kg-viewer")
    if list_viewers:
        kg_viewer.list_views()
        return
    if ctx.invoked_subcommand is not None:
        return
    url = ctx.meta.get(_META_URL)
    if url:
        kg_viewer.open_view(url, new_server)
    else:
        click.echo(ctx.get_help())


@view.command("stop")
@click.argument("target", required=False, default=None)
def view_stop(target):
    """Stop viewer container(s).

    TARGET is an integer id or 'all'. Defaults to the last container on the stack.
    """
    COMP_REGISTRY.get("kg-viewer").stop_views(target)
