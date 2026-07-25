from pathlib import Path

import click

from ._env import EXTRACT_ENV_VARS, docker_env_args
from .configuration import print_config_hint, print_config_status
from .graph_view import view
from .llm import llm_available as _llm_available
from .llm_observability import container_running as _llm_obs_running
from .neo4j import container_running as _neo4j_running

_BUILD_KG_IMAGE = "jejune:extract_knowledge_graph"

_PREFLIGHT_SKIP = {
    "check-availability", "status-availability", "hint-availability",
    "check-config", "status-config", "hint-config",
    "view",
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
    """Build and export the knowledge graph for the current jj_doc_<name> repository."""
    if ctx.invoked_subcommand not in _PREFLIGHT_SKIP:
        _preflight()


graph.add_command(view)


@graph.command("check-availability")
def check_availability():
    """Show detailed graph dependency status (colored per dependency)."""
    deps = _graph_dep_statuses()
    lo_ok, _ = _llm_obs_running()

    def _lbl(ok: bool, name: str, detail: str = "", fg_bad: str = "red") -> str:
        colored = click.style(name, fg="green" if ok else fg_bad)
        return f"{colored}: {detail}" if not ok and detail else colored

    req = ", ".join(_lbl(ok, dep, msg) for dep, (ok, msg) in deps.items())
    opt = f"({_lbl(lo_ok, 'llm-observability', fg_bad='yellow')} optional)"
    click.echo(f"graph: {req} {opt}")


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
