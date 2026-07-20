import shlex
from pathlib import Path

import click

from ._env import EXTRACT_ENV_VARS, TTL_ENV_VARS, docker_env_args

_BUILD_KG_IMAGE = "jejuneness:jj_build_knowledge_graph"
_TTL_IMAGE      = "jejuneness:jj_neo4j_to_rdf_ttl"


def _run(*cmd: str) -> None:
    """Run a command with streamed output; propagate its exit code on failure."""
    import subprocess
    result = subprocess.run(list(cmd))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


@click.group()
def graph():
    """Build and export the knowledge graph for the current jj_doc_* repository."""


@graph.command("extract")
@click.argument("doc_dir", type=click.Path(exists=True))
@click.argument("input_files")
def extract(doc_dir, input_files):
    """Run the Markdown → Neo4j knowledge-graph extraction for DOC_DIR.

    DOC_DIR is the root of a jj_doc_* repository.
    INPUT_FILES is a quoted string of filenames (and optional flags) passed
    to the extractor, e.g. 'file1.md file2.md' or '--flag val file.md'.

    Requires a running Neo4j instance (`jejune neo4j start`).
    Credentials and LLM settings are read from .jejune/env-secrets / environment.
    """
    doc_dir = Path(doc_dir).resolve()

    click.echo(f"Building {_BUILD_KG_IMAGE} ...")
    _run(
        "docker", "build", "-t", _BUILD_KG_IMAGE,
        "https://github.com/EricBoix/jj_build_knowledge_graph.git#:DockerContext",
    )

    click.echo("Running extraction ...")
    _run(
        "docker", "run", "--rm", "--tty",
        "--name", "jj_build_knowledge_graph",
        "--network", "host",
        "-v", f"{doc_dir}:/data",
        *docker_env_args(EXTRACT_ENV_VARS),
        _BUILD_KG_IMAGE,
        "extracting_graph_semantic_chuncker.py",
        "--input_directory", "/data",
        *shlex.split(input_files),
    )


@graph.command("dump-turtle")
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
        "docker", "build", "-t", _TTL_IMAGE,
        "https://github.com/EricBoix/jj_neo4j_to_rdf_ttl.git#:DockerContext",
    )

    click.echo(f"Exporting to {output_dir / filename} ...")
    _run(
        "docker", "run", "--rm",
        "--network", "host",
        "-v", f"{output_dir}:/output",
        *docker_env_args(TTL_ENV_VARS),
        _TTL_IMAGE,
        "neo4j_to_rdf.py", f"/output/{filename}",
    )
