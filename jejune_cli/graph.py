from pathlib import Path

import click

from ._ecosystem import REPO_ROOT_DIR
from ._env import EXTRACT_ENV_VARS, docker_env_args
from .configuration import print_config_hint, print_config_status
from .graph_view import view
from .llm import llm_available as _llm_available
from .llm_observability import container_running as _llm_obs_running
from .neo4j import container_running as _neo4j_running

_BUILD_KG_IMAGE = "jejune:extract_knowledge_graph"

_CHUNKS_JSON = "/data/_chunks.json"

_SPLITTERS = {
    "headers":    "split_by_headers.py",
    "paragraphs": "split_by_paragraphs.py",
    "sentences":  "split_by_sentences.py",
}

_PREFLIGHT_SKIP = {
    "check-availability", "status-availability", "hint-availability",
    "check-config", "status-config", "hint-config",
    "view", "split", "build",
}

_DEP_HINTS = {
    "neo4j": "run `jejune neo4j start`",
    "llm":   "run `jejune llm status`",
}


def _preflight() -> None:
    running, _ = _neo4j_running()
    if not running:
        raise click.ClickException(
            "neo4j is not running — refer to `jejune neo4j start --help`"
        )

    available, msg = _llm_available()
    if not available:
        raise click.ClickException(
            f"llm is not available ({msg}) — refer to `jejune llm status`"
        )


def _run(*cmd: str) -> None:
    """Run a command with streamed output; propagate its exit code on failure."""
    import subprocess

    result = subprocess.run(list(cmd))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _graph_dep_statuses() -> dict[str, tuple[bool, str]]:
    """Run required-dep checks once; shared by graph_available and *-availability commands."""
    return {"neo4j": _neo4j_running(), "llm": _llm_available()}


def graph_available() -> tuple[bool, str]:
    """Return (ok, msg) for graph availability; consumed by catalog.run_all()."""
    deps = _graph_dep_statuses()
    if all(ok for ok, _ in deps.values()):
        return True, "ok"
    return False, "; ".join(f"{dep}: {msg}" for dep, (ok, msg) in deps.items() if not ok)


@click.group(short_help="Build and export the knowledge graph")
@click.pass_context
def graph(ctx):
    """Build and export the knowledge graph for the current jejune_doc_<name> repository."""
    if ctx.invoked_subcommand not in _PREFLIGHT_SKIP:
        _preflight()


graph.add_command(view)


def _build_kg_image() -> None:
    """Build the knowledge-graph extraction Docker image."""
    click.echo(f"Building {_BUILD_KG_IMAGE} ...")
    _run(
        "docker", "build", "-t", _BUILD_KG_IMAGE,
        f"{REPO_ROOT_DIR}/jejune_extract_knowledge_graph.git#:DockerContext",
    )


@graph.command("build")
def graph_build():
    """Build the knowledge-graph extraction Docker image."""
    _build_kg_image()


@graph.command("check-availability")
def check_availability():
    """Show graph availability status with optional-dep detail."""
    ok, msg = graph_available()
    status = click.style("ok", fg="green") if ok else click.style(msg, fg="red")
    lo_ok, _ = _llm_obs_running()
    opt = click.style("llm-observability", fg="green" if lo_ok else "yellow")
    click.echo(f"graph: {status}  ({opt} optional)")


@graph.command("status-availability")
def status_availability():
    """Show graph availability status."""
    ok, _ = graph_available()
    click.echo(f"graph: {click.style('ok', fg='green') if ok else click.style('error', fg='red')}")


@graph.command("hint-availability")
def hint_availability():
    """Show how to fix unavailable graph dependencies."""
    deps = _graph_dep_statuses()
    failing = [dep for dep, (ok, _) in deps.items() if not ok]
    if not failing:
        click.echo(click.style("all graph dependencies are available", fg="green"))
        return
    for dep in failing:
        click.echo(_DEP_HINTS[dep])


@graph.command("check-config")
def check_config():
    """Show per-variable configuration detail for the graph component."""
    from .configuration import print_config_check
    print_config_check("graph")


@graph.command("status-config")
def status_config():
    """Show graph configuration status."""
    print_config_status("graph")


@graph.command("hint-config")
def hint_config():
    """Show the configuration hint for the graph component."""
    print_config_hint("graph")


@graph.command("split", context_settings={"ignore_unknown_options": True})
@click.argument("doc_dir", type=click.Path(exists=True))
@click.option(
    "--splitter",
    type=click.Choice(list(_SPLITTERS)),
    default="headers",
    show_default=True,
    help="Splitting strategy.",
)
@click.option("--output", default=None,
              help="Output JSON path inside the container. Defaults to the splitter's own naming scheme.")
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def split(doc_dir, splitter, output, extra_args):
    """Split DOC_DIR's catalog into JSON chunks.

    Builds the extraction Docker image and runs the chosen splitter script
    against /data/catalog.yaml. Without --output the splitter writes a file
    named after the markdown source and the splitting modality.

    EXTRA_ARGS are forwarded verbatim to the splitter (e.g. --output_dir /data).
    """
    doc_dir = Path(doc_dir).resolve()
    _build_kg_image()

    output_args = ("--output", output) if output is not None else ()
    click.echo(f"Splitting with {_SPLITTERS[splitter]} ...")
    _run(
        "docker", "run", "--rm", "--tty",
        "--network", "host",
        "-v", f"{doc_dir}:/data",
        "--name", "jejune_split",
        _BUILD_KG_IMAGE,
        _SPLITTERS[splitter],
        "--catalog", "/data/catalog.yaml",
        *output_args,
        *extra_args,
    )


@graph.command("extract", context_settings={"ignore_unknown_options": True})
@click.argument("doc_dir", type=click.Path(exists=True))
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def extract(doc_dir, extra_args):
    """Run the Markdown → Neo4j knowledge-graph extraction for DOC_DIR.

    DOC_DIR is the root of a jejune_doc_<name> repository. The command runs
    in two steps using the same Docker image:

    \b
    1. split_by_headers.py  -- splits /data/catalog.yaml into /data/_chunks.json
    2. extract_kg_graph.py  -- feeds the JSON into Neo4j

    EXTRA_ARGS are forwarded verbatim to the extractor (step 2), e.g.
    --load_json_document /data/other.json to blend additional pre-built JSON
    files alongside the auto-generated chunks.

    To use a different splitter or inspect chunks before extraction, run the
    splitter container step manually and call this command with the resulting
    JSON via --load_json_document.

    Requires a running Neo4j instance (`jejune neo4j start`).
    Credentials and LLM settings are read from .jejune/env-secrets / environment.
    """
    doc_dir = Path(doc_dir).resolve()
    _build_kg_image()

    _docker_run = (
        "docker", "run", "--rm", "--tty",
        "--network", "host",
        "-v", f"{doc_dir}:/data",
    )

    click.echo("Splitting document into chunks ...")
    _run(
        *_docker_run,
        "--name", "jejune_split",
        _BUILD_KG_IMAGE,
        _SPLITTERS["headers"],
        "--catalog", "/data/catalog.yaml",
        "--output", _CHUNKS_JSON,
    )

    click.echo("Running extraction ...")
    _run(
        *_docker_run,
        "--name", "jejune_extract_knowledge_graph",
        *docker_env_args(EXTRACT_ENV_VARS),
        _BUILD_KG_IMAGE,
        "extract_kg_graph.py",
        "--load_json_document", _CHUNKS_JSON,
        *extra_args,
    )
