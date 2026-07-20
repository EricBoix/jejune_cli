import shlex
from pathlib import Path

import click

from ._env import EXTRACT_ENV_VARS, docker_env_args
from .configuration import print_config_hint, print_config_status

_BUILD_KG_IMAGE = "jejuneness:extract_knowledge_graph"


def _run(*cmd: str) -> None:
    """Run a command with streamed output; propagate its exit code on failure."""
    import subprocess

    result = subprocess.run(list(cmd))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


@click.group()
def graph():
    """Build and export the knowledge graph for the current jj_doc_<name> repository."""


@graph.command("check-config")
def check_config():
    """Check whether the graph component is properly configured."""
    print_config_status("graph")


@graph.command("hint-config")
def hint_config():
    """Show the configuration hint for the graph component."""
    print_config_hint("graph")


@graph.command("extract")
@click.argument("doc_dir", type=click.Path(exists=True))
@click.argument("input_files")
def extract(doc_dir, input_files):
    """Run the Markdown → Neo4j knowledge-graph extraction for DOC_DIR.

    DOC_DIR is the root of a jj_doc_<name> repository.
    INPUT_FILES is a quoted string of filenames (and optional flags) passed
    to the extractor, e.g. 'file1.md file2.md' or '--flag val file.md'.

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
        *shlex.split(input_files),
    )
