"""Click commands for the Oxigraph triple-store component."""

import webbrowser
from pathlib import Path

import click

from .app_context import AppContext
from .component_cont_oxigraph import CompOxigraph

_KG_VIEWER_IMAGE = "jejune:kg-graph-viewer"
_KG_VIEWER_DEFAULT_PORT = "8782"


def _comp(ctx: click.Context):
    return ctx.find_object(AppContext).component_registry.get("oxigraph")


@click.group(short_help="Manage the Oxigraph triple-store instance")
@click.pass_context
def oxigraph(ctx):
    """Manage the Oxigraph RDF triple-store for the current repository.

    \b
    Data is persisted in OXIGRAPH_DATA_DIR (default: ./.jejune/oxigraph_data).
    Stop and restart are safe — data survives container removal.
    """
    ctx.ensure_object(AppContext)


@oxigraph.command("start")
@click.option(
    "--port", default=None, help="HTTP port (default: OXIGRAPH_HTTP_PORT or 7878)."
)
@click.pass_context
def start(ctx, port):
    """Start the Oxigraph container (standalone workspaces; deployments use `jejune up`)."""
    comp = _comp(ctx)
    _require_standalone(comp)
    running, _ = comp.is_running()
    if running:
        click.echo(click.style("Oxigraph is already running.", fg="green"))
        return
    resolved_port = comp.resolve_port(port)
    data_dir = comp.resolve_data_dir(None)
    click.echo(f"Starting Oxigraph on port {resolved_port}, data at {data_dir} ...")
    comp.launch_container(data_dir, resolved_port)
    click.echo(
        click.style(f"Oxigraph ready on http://localhost:{resolved_port}", fg="green")
    )


@oxigraph.command("stop")
@click.pass_context
def stop(ctx):
    """Stop the Oxigraph container (standalone workspaces; deployments use `jejune down`)."""
    comp = _comp(ctx)
    _require_standalone(comp)
    running, _ = comp.is_running()
    if not running:
        click.echo("Oxigraph is not running.")
        return
    comp.stop()


@oxigraph.command("status")
@click.pass_context
def status(ctx):
    """Show Oxigraph container status and loaded graphs."""
    comp = _comp(ctx)
    running, _ = comp.is_running()
    port = comp.resolve_port(None)
    state = (
        click.style("running", fg="green")
        if running
        else click.style("stopped", fg="yellow")
    )
    click.echo(f"  container   {state}")
    click.echo(f"  port        {port}")
    if running:
        try:
            graphs = comp.list_graphs(port)
            click.echo(f"  graphs      {len(graphs)}")
        except Exception as exc:
            click.echo(f"  graphs      (error: {exc})")


@oxigraph.command("create")
@click.argument("ttl_file", type=click.Path(exists=True))
@click.option("--port", default=None)
@click.pass_context
def create(ctx, ttl_file, port):
    """Load the first TTL_FILE into an empty store.

    Fails if the store already contains data (use 'merge' to add more).
    """
    comp = _comp(ctx)
    _require_running(comp)
    resolved_port = comp.resolve_port(port)
    turtle_path = Path(ttl_file).resolve()
    click.echo(f"Creating store from {turtle_path.name} ...")
    try:
        comp.create_store(resolved_port, turtle_path)
    except RuntimeError as exc:
        raise click.ClickException(str(exc))
    click.echo(click.style("Done.", fg="green"))


@oxigraph.command("merge")
@click.argument("ttl_file", type=click.Path(exists=True))
@click.option("--port", default=None)
@click.pass_context
def merge(ctx, ttl_file, port):
    """Add TTL_FILE to the store and update the alignment graph incrementally."""
    comp = _comp(ctx)
    _require_running(comp)
    resolved_port = comp.resolve_port(port)
    turtle_path = Path(ttl_file).resolve()
    click.echo(f"Merging {turtle_path.name} ...")
    comp.merge_into_store(resolved_port, turtle_path)
    click.echo(click.style("Done.", fg="green"))


@oxigraph.command("graphs")
@click.option("--port", default=None)
@click.pass_context
def graphs(ctx, port):
    """List all named graph URIs in the store."""
    comp = _comp(ctx)
    _require_running(comp)
    resolved_port = comp.resolve_port(port)
    for graph_uri in comp.list_graphs(resolved_port):
        click.echo(f"  {graph_uri}")


@oxigraph.command("realign")
@click.option("--port", default=None)
@click.pass_context
def realign(ctx, port):
    """Recompute the alignment graph from scratch (repair / force rebuild)."""
    comp = _comp(ctx)
    _require_running(comp)
    resolved_port = comp.resolve_port(port)
    click.echo("Recomputing alignment graph ...")
    comp._recompute_alignment(resolved_port)
    click.echo(click.style("Done.", fg="green"))


@oxigraph.command("clear")
@click.option("--port", default=None)
@click.confirmation_option(
    prompt="This will delete all triples in the store. Continue?"
)
@click.pass_context
def clear(ctx, port):
    """Remove all triples from the store (irreversible)."""
    comp = _comp(ctx)
    _require_running(comp)
    resolved_port = comp.resolve_port(port)
    comp.clear_store(resolved_port)
    click.echo(click.style("Store cleared.", fg="green"))


@oxigraph.command("view")
@click.option(
    "--port",
    default=None,
    help=f"Host port for the KG viewer (default: {_KG_VIEWER_DEFAULT_PORT}).",
)
@click.option(
    "--open/--no-open",
    "open_browser",
    default=True,
    help="Open the viewer URL in the default browser (default: open).",
)
@click.pass_context
def view(ctx, port, open_browser):
    """Launch a KG viewer hooked to the running Oxigraph instance.

    \b
    Requires:
      - Oxigraph is already running (jejune oxigraph start, or jejune up in a
        deployment workspace).
      - The image 'jejune:kg-graph-viewer' is built (jejune build).
    """
    app = ctx.find_object(AppContext)
    oxigraph_comp = _comp(ctx)
    _require_running(oxigraph_comp)

    oxigraph_port = _oxigraph_port_from_registry(app)
    oxigraph_url = f"http://localhost:{oxigraph_port}"

    workspace = Path(".").resolve().name.lower()
    container_name = f"jejune-{workspace}-kg-graph-viewer-oxigraph"
    viewer_port = port or _KG_VIEWER_DEFAULT_PORT

    docker = app.component_registry.get("docker-command")

    already_running, _ = docker.is_running(container_name)
    if already_running:
        viewer_url = f"http://localhost:{viewer_port}"
        click.echo(
            click.style(f"KG viewer already running at {viewer_url}", fg="green")
        )
        if open_browser:
            webbrowser.open(viewer_url)
        return

    if not docker.image_exists(_KG_VIEWER_IMAGE):
        raise click.ClickException(
            f"Image '{_KG_VIEWER_IMAGE}' not found — run `jejune build` first."
        )

    click.echo(
        f"Starting KG viewer on port {viewer_port} connected to Oxigraph at"
        f" {oxigraph_url} ..."
    )
    rc = docker.run_detached(
        container_name,
        _KG_VIEWER_IMAGE,
        publish=[f"{viewer_port}:80"],
        env=[f"JEJUNE_OXIGRAPH_URL={oxigraph_url}"],
    )
    if rc != 0:
        raise SystemExit(rc)

    viewer_url = f"http://localhost:{viewer_port}"
    click.echo(click.style(f"KG viewer ready at {viewer_url}", fg="green"))
    if open_browser:
        webbrowser.open(viewer_url)


def _oxigraph_port_from_registry(app) -> str:
    """Return the oxigraph port from the coordination registry, or fall back to default."""
    entries = app.coordination.json_for_component("oxigraph")
    for entry in entries:
        if "port" in entry:
            return str(entry["port"])
    return CompOxigraph._DEFAULT_PORT


def _require_running(comp) -> None:
    running, _ = comp.is_running()
    if not running:
        raise click.ClickException(comp.not_running_message)


def _require_standalone(comp) -> None:
    try:
        comp.require_standalone()
    except RuntimeError as exc:
        raise click.ClickException(str(exc))
