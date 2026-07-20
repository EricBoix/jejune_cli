import os
import subprocess
import time
from pathlib import Path

import click

_NEO4J_CONTAINER = "jj_neo4j_db"
_NEO4J_IMAGE = "jejuneness:jj_neo4j_docker"


def _run(*cmd: str) -> None:
    """Run a command with streamed output; propagate its exit code on failure."""
    result = subprocess.run(list(cmd))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _stop_quiet() -> None:
    """Stop and remove the Neo4j container, ignoring errors."""
    subprocess.run(["docker", "stop", _NEO4J_CONTAINER], stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "rm",   _NEO4J_CONTAINER], stderr=subprocess.DEVNULL)


@click.group()
def neo4j():
    """Manage the Neo4j instance for the current jj_doc_* repository."""


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
    data_dir = Path(data_dir).resolve()

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

    click.echo(f"Building {_NEO4J_IMAGE} ...")
    _run("docker", "build", "-t", _NEO4J_IMAGE,
         "https://github.com/EricBoix/jj_neo4j_docker.git")

    (data_dir / "database").mkdir(parents=True, exist_ok=True)

    click.echo(f"Starting Neo4j on bolt port {port} ...")
    _run(
        "docker", "run", "--rm", "--detach",
        "--name", _NEO4J_CONTAINER,
        "--publish", "7474:7474",
        "--publish", f"{port}:7687",
        "--env", f"NEO4J_AUTH={credentials}",
        "-v", f"{data_dir}/database:/data",
        _NEO4J_IMAGE,
    )

    click.echo("Waiting for container to be running ", nl=False)
    while True:
        probe = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", _NEO4J_CONTAINER],
            capture_output=True, text=True,
        )
        if probe.stdout.strip() == "true":
            break
        click.echo(".", nl=False)
        time.sleep(0.5)
    click.echo()
    click.echo("Waiting for Neo4j to finish initializing (5 s) ...")
    time.sleep(5)
    click.echo(f"Neo4j ready on bolt port {port}.")


@neo4j.command("stop")
def stop():
    """Stop and remove the Neo4j Docker container."""
    click.echo(f"Stopping {_NEO4J_CONTAINER} ...")
    subprocess.run(["docker", "stop", _NEO4J_CONTAINER], stderr=subprocess.DEVNULL)
    click.echo(f"Removing {_NEO4J_CONTAINER} ...")
    subprocess.run(["docker", "rm",   _NEO4J_CONTAINER], stderr=subprocess.DEVNULL)
    click.echo("Neo4j stopped.")


@neo4j.command("dump")
@click.argument("results_dir", type=click.Path())
@click.argument("dump_filename")
def dump(results_dir, dump_filename):
    """Dump the Neo4j database to RESULTS_DIR/backups/DUMP_FILENAME.

    RESULTS_DIR must contain a database/ subdirectory.
    Neo4j is stopped before dumping (required by neo4j-admin).

    \b
    Warning: credentials are burnt into the dump file.
    Keep the (dump, username, password) triplet together.
    """
    results_dir = Path(results_dir).resolve()
    database_dir = results_dir / "database"
    backups_dir  = results_dir / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    click.echo("Stopping Neo4j (required before dump) ...")
    _stop_quiet()

    click.echo("Dumping database ...")
    _run(
        "docker", "run", "--interactive", "--tty", "--rm",
        f"--volume={database_dir}:/data",
        f"--volume={backups_dir}:/output",
        "neo4j/neo4j-admin",
        "neo4j-admin", "database", "dump", "neo4j", "--to-path=/output",
    )

    # neo4j-admin does not allow choosing the output filename; rename afterwards
    (backups_dir / "neo4j.dump").rename(backups_dir / dump_filename)
    click.echo(f"Dump written to {backups_dir / dump_filename}.")


@neo4j.command("restore")
@click.argument("results_dir", type=click.Path())
@click.argument("dump_filename")
def restore(results_dir, dump_filename):
    """Restore the Neo4j database from RESULTS_DIR/backups/DUMP_FILENAME.

    Stops Neo4j, wipes the current database directory, then loads the dump.
    The username/password burnt into the dump must match the target instance.
    """
    import shutil
    results_dir  = Path(results_dir).resolve()
    database_dir = results_dir / "database"
    backups_dir  = results_dir / "backups"
    dump_path    = backups_dir / dump_filename

    if not dump_path.exists():
        raise click.ClickException(f"Dump file not found: {dump_path}")

    click.echo("Stopping Neo4j (required before restore) ...")
    _stop_quiet()

    click.echo("Wiping current database ...")
    shutil.rmtree(database_dir, ignore_errors=True)

    # neo4j-admin load expects the source file to be named neo4j.dump
    neo4j_dump_path = backups_dir / "neo4j.dump"
    shutil.copy2(dump_path, neo4j_dump_path)

    click.echo(f"Restoring from {dump_path} ...")
    _run(
        "docker", "run", "--interactive", "--tty", "--rm",
        f"--volume={database_dir}:/data",
        f"--volume={backups_dir}:/backups",
        "neo4j/neo4j-admin",
        "neo4j-admin", "database", "load", "neo4j", "--from-path=/backups",
    )
    click.echo("Restore complete.")
