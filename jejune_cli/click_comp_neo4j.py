import os
from pathlib import Path

import click

from .click_comp_configuration import (
    print_config_check,
    print_config_hint,
    print_config_status,
)

from .component_cont_neo4j import neo4j_comp



def _launch_container(data_dir: Path, port: str, credentials: str) -> None:
    click.echo(f"Starting Neo4j on bolt port {port} ...")
    neo4j_comp.launch_container(data_dir, port, credentials)
    click.echo(f"Neo4j ready on bolt port {port}.")


@click.group(short_help="Manage the Neo4j instance")
def neo4j():
    """Manage the Neo4j instance for the current jejune_doc_<name> repository."""


@neo4j.command("check-config")
def check_config():
    """Show per-variable configuration detail for the neo4j component."""
    print_config_check(neo4j_comp.configuration)


@neo4j.command("status-config")
def status_config():
    """Show neo4j configuration status."""
    print_config_status(neo4j_comp.configuration)


@neo4j.command("hint-config")
def hint_config():
    """Show the configuration hint for the neo4j component."""
    print_config_hint(neo4j_comp.configuration)


@neo4j.command("check-availability")
def check_availability():
    """Show detailed neo4j availability (container state and bolt endpoint)."""
    cfg_status, _, hint = neo4j_comp.configuration.check()
    if cfg_status != "ok":
        click.echo(f"  {click.style('not configured', fg='yellow')}  {hint}")
        return
    running, _ = neo4j_comp.is_running()
    port = os.environ.get("NEO4J_PORT", "7687")
    click.echo(
        f"  container   {click.style('running', fg='green') if running else click.style('not running', fg='yellow')}"
    )
    click.echo(f"  bolt        bolt://localhost:{port}")


@neo4j.command("status-availability")
def status_availability():
    """Show neo4j availability status."""
    cfg_status, *_ = neo4j_comp.configuration.check()
    if cfg_status != "ok":
        click.echo(f"neo4j: {click.style('not configured', fg='yellow')}")
        return
    running, msg = neo4j_comp.is_running()
    if running:
        click.echo(f"neo4j: {click.style('ok', fg='green')}")
    else:
        click.echo(f"neo4j: {click.style(msg, fg='yellow')}")


@neo4j.command("hint-availability")
def hint_availability():
    """Show how to start Neo4j if it is not running."""
    running, _ = neo4j_comp.is_running()
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
def stats(simple, assert_counts):
    """Print a node and relationship summary of the running Neo4j database."""
    running, _ = neo4j_comp.is_running()
    if not running:
        raise click.ClickException(
            "neo4j is not running — start it first with `jejune neo4j start`"
        )
    try:
        total_nodes, nodes_by_label, total_relationships, relationships_by_type = (
            neo4j_comp.stats()
        )
    except RuntimeError as e:
        raise click.ClickException(str(e))

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
def start(data_dir, port, credentials):
    """Launch the Neo4j Docker container, storing files in DATA_DIR/database/.

    DATA_DIR must be an absolute path.
    Requires NEO4J_USERNAME and NEO4J_PASSWORD (or --credentials USER/PASSWORD).
    """
    running, _ = neo4j_comp.is_running()
    if running:
        click.echo(click.style("Neo4j is already running — nothing to do.", fg="green"))
        return
    data_dir = Path(data_dir).resolve()
    try:
        port, credentials = neo4j_comp.resolve_port_credentials(port, credentials)
    except ValueError as e:
        raise click.ClickException(str(e))
    _launch_container(data_dir, port, credentials)


@neo4j.command("stop")
def stop():
    """Stop and remove the Neo4j Docker container."""
    neo4j_comp.stop()


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
def delete(data_dir, port, credentials):
    """Delete all Neo4j data (databases and transactions) and restart fresh.

    Stops Neo4j if running, wipes DATA_DIR/database/, then starts a clean instance.
    DATA_DIR must be the same directory used with `jejune neo4j start`.
    Requires NEO4J_USERNAME and NEO4J_PASSWORD (or --credentials USER/PASSWORD).
    """
    data_dir = Path(data_dir).resolve()
    database_dir = data_dir / "database"
    try:
        port, credentials = neo4j_comp.resolve_port_credentials(port, credentials)
    except ValueError as e:
        raise click.ClickException(str(e))

    neo4j_comp.delete()

    click.echo(f"Wiping {database_dir} ...")
    neo4j_comp.wipe_database(database_dir)

    _launch_container(data_dir, port, credentials)


@neo4j.command("dump")
@click.argument("results_dir", type=click.Path())
@click.argument("dump_filename")
def dump(results_dir, dump_filename):
    """Dump the Neo4j database to RESULTS_DIR/backups/DUMP_FILENAME.

    RESULTS_DIR must contain a database/ subdirectory.
    Requires Neo4j to be stopped first (run `jejune neo4j stop`).

    \b
    Warning: credentials are burnt into the dump file.
    Keep the (dump, username, password) triplet together.
    """
    results_dir = Path(results_dir).resolve()
    click.echo("Dumping database ...")
    try:
        out = neo4j_comp.dump(results_dir, dump_filename)
    except RuntimeError as e:
        raise click.ClickException(str(e))
    click.echo(f"Dump written to {out}.")


@neo4j.command("restore")
@click.argument("results_dir", type=click.Path())
@click.argument("dump_filename")
def restore(results_dir, dump_filename):
    """Restore the Neo4j database from RESULTS_DIR/backups/DUMP_FILENAME.

    Requires Neo4j to be stopped first (run `jejune neo4j stop`).
    Wipes the current database directory, then loads the dump.
    The username/password burnt into the dump must match the target instance.
    """
    results_dir = Path(results_dir).resolve()
    click.echo(f"Restoring {dump_filename} ...")
    try:
        neo4j_comp.restore(results_dir, dump_filename)
    except RuntimeError as e:
        raise click.ClickException(str(e))
    click.echo("Restore complete.")


from . import click_comp_neo4j_to_rdf_ttl  # noqa: E402, F401
