from pathlib import Path

import click

from ._env import EXTRACT_ENV_VARS, docker_env_args
from .configuration import print_config_hint, print_config_status
from .graph_view import view
from .llm import llm_available as _llm_available
from .neo4j import container_running as _neo4j_running

_BUILD_KG_IMAGE = "jejune:extract_knowledge_graph"

_PREFLIGHT_SKIP = {"check-config", "hint-config", "view"}


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


@click.group(short_help="Build and export the knowledge graph")
@click.pass_context
def graph(ctx):
    """Build and export the knowledge graph for the current jj_doc_<name> repository."""
    if ctx.invoked_subcommand not in _PREFLIGHT_SKIP:
        _preflight()


graph.add_command(view)


@graph.command("check-config")
def check_config():
    """Check whether the graph component is properly configured."""
    print_config_status("graph")


@graph.command("hint-config")
def hint_config():
    """Show the configuration hint for the graph component."""
    print_config_hint("graph")


@graph.command("extract", context_settings={"ignore_unknown_options": True})
@click.argument("doc_dir", type=click.Path(exists=True))
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def extract(doc_dir, extra_args):
    """Run the Markdown → Neo4j knowledge-graph extraction for DOC_DIR.

    DOC_DIR is the root of a jj_doc_<name> repository.
    EXTRA_ARGS are filenames and flags forwarded verbatim to the extractor,
    e.g. file1.md file2.md or --load_markdown_document file.md.

    Requires a running Neo4j instance (`jejune neo4j start`).
    Credentials and LLM settings are read from .jejune/env-secrets / environment.
    """
    doc_dir = Path(doc_dir).resolve()

    click.echo(f"Building {_BUILD_KG_IMAGE} ...")
    _run(
        "docker",
        "build",
        "-t",
        _BUILD_KG_IMAGE,
        "https://github.com/EricBoix/jejune_extract_knowledge_graph.git#:DockerContext",
    )

    click.echo("Running extraction ...")
    _run(
        "docker",
        "run",
        "--rm",
        "--tty",
        "--name",
        "jejune_extract_knowledge_graph",
        "--network",
        "host",
        "-v",
        f"{doc_dir}:/data",
        *docker_env_args(EXTRACT_ENV_VARS),
        _BUILD_KG_IMAGE,
        "extracting_graph_semantic_chuncker.py",
        "--input_directory",
        "/data",
        *extra_args,
    )
