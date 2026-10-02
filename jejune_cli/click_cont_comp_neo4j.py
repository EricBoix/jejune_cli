import os
from pathlib import Path

import click

from .app_context import AppContext
from .click_configuration import (
    print_config_check,
    print_config_hint,
    print_config_status,
)
from .click_cont_comp_neo4j_helpers import resolve_llm_decorated_filename
from .click_cont_comp_neo4j_to_rdf_ttl import dump_turtle


def _launch_container(neo4j_comp, data_dir: Path, port: str, credentials: str) -> None:
    click.echo(f"Starting Neo4j on bolt port {port} ...")
    neo4j_comp.launch_container(data_dir, port, credentials)
    click.echo(f"Neo4j ready on bolt port {port}.")


@click.group(short_help="Manage the Neo4j instance")
@click.pass_context
def neo4j(ctx):
    """Manage the Neo4j instance for the current jejune_doc_<name> repository."""
    ctx.obj = ctx.find_object(AppContext).component_registry.get("neo4j")


@neo4j.command("check-config")
@click.pass_obj
def check_config(comp):
    """Show per-variable configuration detail for the neo4j component."""
    print_config_check(comp.configuration)


@neo4j.command("status-config")
@click.pass_obj
def status_config(comp):
    """Show neo4j configuration status."""
    print_config_status(comp.configuration)


@neo4j.command("hint-config")
@click.pass_obj
def hint_config(comp):
    """Show the configuration hint for the neo4j component."""
    print_config_hint(comp.configuration)


@neo4j.command("check-availability")
@click.pass_obj
def check_availability(comp):
    """Show detailed neo4j availability (container state and bolt endpoint)."""
    cfg_status, _, hint = comp.configuration.check()
    if cfg_status != "ok":
        click.echo(f"  {click.style('not configured', fg='yellow')}  {hint}")
        return
    running, _ = comp.is_running()
    port = os.environ.get("NEO4J_PORT", "7687")
    click.echo(
        f"  container   {click.style('running', fg='green') if running else click.style('not running', fg='yellow')}"
    )
    click.echo(f"  bolt        bolt://localhost:{port}")


@neo4j.command("status-availability")
@click.pass_obj
def status_availability(comp):
    """Show neo4j availability status."""
    cfg_status, *_ = comp.configuration.check()
    if cfg_status != "ok":
        click.echo(f"neo4j: {click.style('not configured', fg='yellow')}")
        return
    running, msg = comp.is_running()
    if running:
        click.echo(f"neo4j: {click.style('ok', fg='green')}")
    else:
        click.echo(f"neo4j: {click.style(msg, fg='yellow')}")


@neo4j.command("hint-availability")
@click.pass_obj
def hint_availability(comp):
    """Show how to start Neo4j if it is not running."""
    running, _ = comp.is_running()
    if running:
        click.echo(click.style("neo4j is running", fg="green"))
    else:
        click.echo("run `jejune neo4j start`")


@neo4j.command("stats")
@click.option(
    "--simple",
    is_flag=True,
    default=False,
    help="Output only total counts as #nodes/#relationships.",
)
@click.option(
    "--assert",
    "assert_counts",
    default=None,
    metavar="NODES/RELATIONSHIPS",
    help="Assert current counts match NODES/RELATIONSHIPS; exit 1 if not.",
)
@click.pass_obj
def stats(comp, simple, assert_counts):
    """Print a node and relationship summary of the running Neo4j database."""
    running, _ = comp.is_running()
    if not running:
        raise click.ClickException(
            "neo4j is not running — start it first with `jejune neo4j start`"
        )
    try:
        total_nodes, nodes_by_label, total_relationships, relationships_by_type = (
            comp.stats()
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc))

    if assert_counts is not None:
        try:
            expected_nodes, expected_relationships = (
                int(x) for x in assert_counts.split("/")
            )
        except ValueError:
            raise click.BadParameter(
                "must be in the form <int>/<int>", param_hint="'--assert'"
            )
        actual = f"{total_nodes}/{total_relationships}"
        if (
            total_nodes == expected_nodes
            and total_relationships == expected_relationships
        ):
            click.echo(f"ok  {actual}")
        else:
            raise click.ClickException(
                f"assertion failed — expected {assert_counts}, got {actual}"
            )
        return

    if simple:
        click.echo(f"{total_nodes}/{total_relationships}")
        return

    w = max((len(label) for label, _ in nodes_by_label), default=0)
    w = max(
        w,
        max((len(t) for t, _ in relationships_by_type), default=0),
        len("Relationships"),
    )

    click.echo(f"{'Nodes':<{w}} : {total_nodes:>8}")
    for label, count in nodes_by_label:
        click.echo(f"  {label:<{w}} {count:>8}")
    click.echo()
    click.echo(f"{'Relationships':<{w}} : {total_relationships:>8}")
    for rel_type, count in relationships_by_type:
        click.echo(f"  {rel_type:<{w}} {count:>8}")


@neo4j.command("start")
@click.argument("data_dir", type=click.Path())
@click.option(
    "--port",
    default=None,
    help="Bolt port for the Neo4j server (default: NEO4J_PORT env var, fallback 7687).",
)
@click.option(
    "--credentials",
    default=None,
    metavar="USER/PASSWORD",
    help="Neo4j auth string (default: NEO4J_USERNAME/NEO4J_PASSWORD env vars).",
)
@click.pass_obj
def start(comp, data_dir, port, credentials):
    """Launch the Neo4j Docker container, storing files in DATA_DIR/database/.

    DATA_DIR must be an absolute path.
    Requires NEO4J_USERNAME and NEO4J_PASSWORD (or --credentials USER/PASSWORD).
    """
    running, _ = comp.is_running()
    if running:
        click.echo(click.style("Neo4j is already running — nothing to do.", fg="green"))
        return
    data_dir = Path(data_dir).resolve()
    try:
        port, credentials = comp.resolve_port_credentials(port, credentials)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    _launch_container(comp, data_dir, port, credentials)


@neo4j.command("stop")
@click.pass_obj
def stop(comp):
    """Stop and remove the Neo4j Docker container."""
    comp.stop()


@neo4j.command("delete")
@click.argument("data_dir", type=click.Path())
@click.option(
    "--port",
    default=None,
    help="Bolt port for the restarted Neo4j server (default: NEO4J_PORT env var, fallback 7687).",
)
@click.option(
    "--credentials",
    default=None,
    metavar="USER/PASSWORD",
    help="Neo4j auth string (default: NEO4J_USERNAME/NEO4J_PASSWORD env vars).",
)
@click.pass_obj
def delete(comp, data_dir, port, credentials):
    """Delete all Neo4j data (databases and transactions) and restart fresh.

    Stops Neo4j if running, wipes DATA_DIR/database/, then starts a clean instance.
    DATA_DIR must be the same directory used with `jejune neo4j start`.
    Requires NEO4J_USERNAME and NEO4J_PASSWORD (or --credentials USER/PASSWORD).
    """
    data_dir = Path(data_dir).resolve()
    database_dir = data_dir / "database"
    try:
        port, credentials = comp.resolve_port_credentials(port, credentials)
    except ValueError as exc:
        raise click.ClickException(str(exc))

    try:
        comp._preflight_database_dir_ownership(database_dir)
    except RuntimeError as exc:
        raise click.ClickException(str(exc))
    comp.delete()

    click.echo(f"Wiping {database_dir} ...")
    comp.wipe_database(database_dir)

    _launch_container(comp, data_dir, port, credentials)


@neo4j.command("dump")
@click.argument("results_dir", type=click.Path())
@click.argument("dump_filename")
@click.pass_obj
def dump(comp, results_dir, dump_filename):
    """Dump the Neo4j database to RESULTS_DIR/backups/DUMP_FILENAME.

    Neo4j must be running. The command queries the LLM model name(s) from
    the database, decorates DUMP_FILENAME with them, stops Neo4j, performs
    the dump, then restarts Neo4j.

    \b
    Warning: credentials are burnt into the dump file.
    Keep the (dump, username, password) triplet together.
    """
    results_dir = Path(results_dir).resolve()
    running, _ = comp.is_running()
    if not running:
        raise click.ClickException(
            "Neo4j is not running — start it first with `jejune neo4j start`"
        )
    dump_filename = resolve_llm_decorated_filename(comp, dump_filename)
    try:
        port, credentials = comp.resolve_port_credentials(port=None, credentials=None)
    except ValueError as error:
        raise click.ClickException(str(error))

    comp.stop()

    click.echo("Dumping database ...")
    try:
        out = comp.dump(results_dir, dump_filename)
    except RuntimeError as error:
        raise click.ClickException(str(error))
    click.echo(f"Dump written to {out}.")

    _launch_container(comp, results_dir, port, credentials)


@neo4j.command("restore")
@click.argument("results_dir", type=click.Path())
@click.argument("dump_filename")
@click.pass_obj
def restore(comp, results_dir, dump_filename):
    """Restore the Neo4j database from RESULTS_DIR/backups/DUMP_FILENAME.

    Requires Neo4j to be stopped first (run `jejune neo4j stop`).
    Wipes the current database directory, then loads the dump.
    The username/password burnt into the dump must match the target instance.
    """
    results_dir = Path(results_dir).resolve()
    click.echo(f"Restoring {dump_filename} ...")
    try:
        comp.restore(results_dir, dump_filename)
    except RuntimeError as exc:
        raise click.ClickException(str(exc))
    click.echo("Restore complete.")


neo4j.add_command(dump_turtle)
