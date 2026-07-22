import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import click

from ._env import TTL_ENV_VARS, docker_env_args
from .configuration import (
    component_config_check,
    print_config_hint,
    print_config_status,
)

_NEO4J_CONTAINER = "jejune_neo4j"
_NEO4J_IMAGE = "jejune:neo4j"
_TTL_IMAGE = "jejune:neo4j_to_rdf_ttl"


def _run(*cmd: str) -> None:
    """Run a command with streamed output; propagate its exit code on failure."""
    result = subprocess.run(list(cmd))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def container_running() -> tuple[bool, str]:
    """Return (is_running, message) for the Neo4j container."""
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", _NEO4J_CONTAINER],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        return False, "not started"
    return True, "ok"


def _wipe_database(database_dir: Path) -> None:
    """Remove the Neo4j database directory entirely."""
    import shutil

    click.echo(f"Wiping {database_dir} ...")
    shutil.rmtree(database_dir, ignore_errors=True)


def _require_stopped() -> None:
    """Raise ClickException if the Neo4j container is currently running."""
    running, _ = container_running()
    if running:
        raise click.ClickException(
            "neo4j is running — stop it first with `jejune neo4j stop`"
        )


def _resolve_port_credentials(
    port: str | None, credentials: str | None
) -> tuple[str, str]:
    """Resolve port and credentials from explicit args or environment variables."""
    if port is None:
        port = os.environ.get("NEO4J_PORT", "7687")
    if credentials is None:
        user = os.environ.get("NEO4J_USERNAME")
        password = os.environ.get("NEO4J_PASSWORD")
        if not user or not password:
            raise click.ClickException(
                "Provide --credentials USER/PASSWORD or set NEO4J_USERNAME and NEO4J_PASSWORD."
            )
        credentials = f"{user}/{password}"
    return port, credentials


def _launch_container(data_dir: Path, port: str, credentials: str) -> None:
    """Build the Neo4j image, start the container, and wait until it is ready."""
    click.echo(f"Building {_NEO4J_IMAGE} ...")
    _run(
        "docker",
        "build",
        "-t",
        _NEO4J_IMAGE,
        "https://github.com/EricBoix/jejune_neo4j_docker.git",
    )

    (data_dir / "database").mkdir(parents=True, exist_ok=True)

    click.echo(f"Starting Neo4j on bolt port {port} ...")
    _run(
        "docker",
        "run",
        "--rm",
        "--detach",
        "--name",
        _NEO4J_CONTAINER,
        "--publish",
        "7474:7474",
        "--publish",
        f"{port}:7687",
        "--env",
        f"NEO4J_AUTH={credentials}",
        "-v",
        f"{data_dir}/database:/data",
        _NEO4J_IMAGE,
    )

    click.echo("Waiting for container to be running ", nl=False)
    while True:
        probe = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", _NEO4J_CONTAINER],
            capture_output=True,
            text=True,
        )
        if probe.stdout.strip() == "true":
            break
        click.echo(".", nl=False)
        time.sleep(0.5)
    click.echo()
    click.echo("Waiting for Neo4j to finish initializing (5 s) ...")
    time.sleep(5)
    click.echo(f"Neo4j ready on bolt port {port}.")


@click.group(short_help="Manage the Neo4j instance")
def neo4j():
    """Manage the Neo4j instance for the current jj_doc_<name> repository."""


@neo4j.command("check-config")
def check_config():
    """Check whether the neo4j component is properly configured."""
    print_config_status("neo4j")


@neo4j.command("hint-config")
def hint_config():
    """Show the configuration hint for the neo4j component."""
    print_config_hint("neo4j")


@neo4j.command("status")
def status():
    """Report the Neo4j container state."""
    cfg_status, hint = component_config_check("neo4j")
    if cfg_status != "ok":
        click.echo(f"  {click.style('not configured', fg='yellow')}  {hint}")
        return

    running, _ = container_running()
    port = os.environ.get("NEO4J_PORT", "7687")

    if running:
        container_text = click.style("running", fg="green")
    else:
        container_text = click.style("not running", fg="yellow")
    click.echo(f"  container   {container_text}")
    click.echo(f"  bolt        bolt://localhost:{port}")


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
    running, _ = container_running()
    if not running:
        raise click.ClickException(
            "neo4j is not running — start it first with `jejune neo4j start`"
        )

    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    token = base64.b64encode(f"{user}:{password}".encode()).decode()

    payload = json.dumps(
        {
            "statements": [
                {"statement": "MATCH (n) RETURN count(n) AS count"},
                {
                    "statement": "MATCH (n) UNWIND labels(n) AS label "
                    "RETURN label, count(*) AS count ORDER BY count DESC"
                },
                {"statement": "MATCH ()-[r]->() RETURN count(r) AS count"},
                {
                    "statement": "MATCH ()-[r]->() "
                    "RETURN type(r) AS type, count(*) AS count ORDER BY count DESC"
                },
            ]
        }
    ).encode()

    req = urllib.request.Request(
        "http://localhost:7474/db/neo4j/tx/commit",
        data=payload,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise click.ClickException(f"could not reach Neo4j HTTP API: {e.reason}")

    if data.get("errors"):
        raise click.ClickException(f"Neo4j error: {data['errors'][0]['message']}")

    results = data["results"]
    total_nodes = results[0]["data"][0]["row"][0]
    nodes_by_label = [(r["row"][0], r["row"][1]) for r in results[1]["data"]]
    total_relationships = results[2]["data"][0]["row"][0]
    relationships_by_type = [(r["row"][0], r["row"][1]) for r in results[3]["data"]]

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
    running, _ = container_running()
    if running:
        click.echo(click.style("Neo4j is already running — nothing to do.", fg="green"))
        return
    data_dir = Path(data_dir).resolve()
    port, credentials = _resolve_port_credentials(port, credentials)
    _launch_container(data_dir, port, credentials)


@neo4j.command("stop")
def stop():
    """Stop and remove the Neo4j Docker container."""
    click.echo(f"Stopping {_NEO4J_CONTAINER} ...")
    subprocess.run(["docker", "stop", _NEO4J_CONTAINER], stderr=subprocess.DEVNULL)
    click.echo(f"Removing {_NEO4J_CONTAINER} ...")
    subprocess.run(["docker", "rm", _NEO4J_CONTAINER], stderr=subprocess.DEVNULL)
    click.echo("Neo4j stopped.")


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
    port, credentials = _resolve_port_credentials(port, credentials)

    running, _ = container_running()
    if running:
        click.echo(f"Stopping {_NEO4J_CONTAINER} ...")
        subprocess.run(["docker", "stop", _NEO4J_CONTAINER], stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "rm", _NEO4J_CONTAINER], stderr=subprocess.DEVNULL)

    _wipe_database(database_dir)

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
    database_dir = results_dir / "database"
    backups_dir = results_dir / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    _require_stopped()

    existing = backups_dir / "neo4j.dump"
    if existing.exists():
        raise click.ClickException(f"{existing} already exists — remove it first")

    click.echo("Dumping database ...")
    _run(
        "docker",
        "run",
        "--interactive",
        "--tty",
        "--rm",
        f"--volume={database_dir}:/data",
        f"--volume={backups_dir}:/output",
        "neo4j/neo4j-admin",
        "neo4j-admin",
        "database",
        "dump",
        "neo4j",
        "--to-path=/output",
    )

    # neo4j-admin does not allow choosing the output filename; rename afterwards
    (backups_dir / "neo4j.dump").rename(backups_dir / dump_filename)
    click.echo(f"Dump written to {backups_dir / dump_filename}.")


@neo4j.command("dump-turtle")
@click.argument("output_dir", type=click.Path())
@click.argument("filename")
def dump_turtle(output_dir, filename):
    """Export the Neo4j knowledge graph to OUTPUT_DIR/FILENAME (RDF/Turtle).

    Requires a running Neo4j instance populated by `jejune graph extract`.
    Neo4j credentials are read from .jejune/env-secrets / environment.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Building {_TTL_IMAGE} ...")
    _run(
        "docker",
        "build",
        "-t",
        _TTL_IMAGE,
        "https://github.com/EricBoix/jj_neo4j_to_rdf_ttl.git#:DockerContext",
    )

    click.echo(f"Exporting to {output_dir / filename} ...")
    _run(
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "-v",
        f"{output_dir}:/output",
        *docker_env_args(TTL_ENV_VARS),
        _TTL_IMAGE,
        "neo4j_to_rdf.py",
        f"/output/{filename}",
    )


@neo4j.command("restore")
@click.argument("results_dir", type=click.Path())
@click.argument("dump_filename")
def restore(results_dir, dump_filename):
    """Restore the Neo4j database from RESULTS_DIR/backups/DUMP_FILENAME.

    Requires Neo4j to be stopped first (run `jejune neo4j stop`).
    Wipes the current database directory, then loads the dump.
    The username/password burnt into the dump must match the target instance.
    """
    import shutil

    results_dir = Path(results_dir).resolve()
    database_dir = results_dir / "database"
    backups_dir = results_dir / "backups"
    dump_path = backups_dir / dump_filename

    if not dump_path.exists():
        raise click.ClickException(f"Dump file not found: {dump_path}")

    _require_stopped()

    _wipe_database(database_dir)

    # neo4j-admin load expects the source file to be named neo4j.dump
    neo4j_dump_path = backups_dir / "neo4j.dump"
    shutil.copy2(dump_path, neo4j_dump_path)

    click.echo(f"Restoring from {dump_path} ...")
    _run(
        "docker",
        "run",
        "--interactive",
        "--tty",
        "--rm",
        f"--volume={database_dir}:/data",
        f"--volume={backups_dir}:/backups",
        "neo4j/neo4j-admin",
        "neo4j-admin",
        "database",
        "load",
        "neo4j",
        "--from-path=/backups",
    )
    click.echo("Restore complete.")
