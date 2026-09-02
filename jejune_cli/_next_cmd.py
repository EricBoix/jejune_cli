"""Next-step command group and heuristic registrations."""
import click

from ._env import dot_jejune
from .next_steps import (
    HeuristicStep,
    command_viable,
    evaluate,
    evaluate_state,
    register_command_precondition,
    register_heuristic,
    register_precondition,
)


@click.group("next", invoke_without_command=True, short_help="Show suggested next actions given the current context.")
@click.pass_context
def next_cmd(ctx):
    """Show suggested next actions given the current context."""
    if ctx.invoked_subcommand is not None:
        return
    steps = evaluate()
    if not steps:
        if command_viable("jejune doctor"):
            click.echo("No next steps detected. Run `jejune doctor` for system status.")
        else:
            from .role import detect_role
            active_role, _ = detect_role()
            if active_role in (None, "doc-steward") and not dot_jejune().is_dir():
                click.echo(
                    "No next steps detected. "
                    "Run `jejune configuration doc-steward init` to set up the workspace."
                )
            else:
                click.echo("No next steps detected.")
        return
    click.echo("Suggested next steps:")
    for s in steps:
        cmd = s.resolved_command()
        suffix = f"  →  {cmd}" if cmd else ""
        click.echo(f"  • {s.label}{suffix}")


@next_cmd.command("state")
@click.option("--list-preconditions", is_flag=True, default=False,
              help="List all registered preconditions with their current status.")
def next_state_cmd(list_preconditions: bool) -> None:
    """Show condition evaluation for all registered heuristic rules."""
    from .next_steps import _NAMED_PRECONDITIONS, _PRECONDITIONS

    if list_preconditions:
        if _NAMED_PRECONDITIONS:
            click.echo("Preconditions:")
            _W = max(len(n) for n in _NAMED_PRECONDITIONS)
            for name in sorted(_NAMED_PRECONDITIONS):
                try:
                    val = _NAMED_PRECONDITIONS[name]()
                except Exception:
                    val = False
                mark = click.style("✓", fg="green") if val else click.style("✗", fg="red")
                click.echo(f"  {mark} {name:<{_W}}")

        if _PRECONDITIONS:
            if _NAMED_PRECONDITIONS:
                click.echo()
            click.echo("Command preconditions:")
            _W = max(len(cmd) for cmd in _PRECONDITIONS)
            for cmd in sorted(_PRECONDITIONS):
                try:
                    viable = _PRECONDITIONS[cmd]()
                except Exception:
                    viable = False
                mark = click.style("viable", fg="green") if viable else click.style("blocked", fg="red")
                click.echo(f"  {cmd:<{_W}}  {mark}")

        if not _NAMED_PRECONDITIONS and not _PRECONDITIONS:
            click.echo("No preconditions registered.")
        return

    entries = evaluate_state()
    if not entries:
        click.echo("No heuristic rules registered.")
        return
    for step, cond_results, anti_results in entries:
        active = all(v for _, v in cond_results) and not any(v for _, v in anti_results)
        mark = click.style("✓", fg="green") if active else click.style("✗", fg="red")
        cmd = step.resolved_command()
        cmd_hint = f"  ({cmd})" if cmd else ""
        click.echo(f"  {mark} {step.label}{cmd_hint}  [order {step.order}]")
        for name, val in cond_results:
            cmark = click.style("✓", fg="green") if val else click.style("✗", fg="red")
            click.echo(f"       {cmark} {name}")
        for name, val in anti_results:
            amark = click.style("✓", fg="red") if val else click.style("✗", fg="green")
            suffix = "  (blocking)" if val else "  (not blocking)"
            click.echo(f"       anti: {amark} {name}{suffix}")
        click.echo()


# ---------------------------------------------------------------------------
# Heuristic condition functions
# ---------------------------------------------------------------------------

def _is_role_set() -> bool:
    """True when role is explicitly set via a valid .jejune/role file."""
    from .role import detect_role
    _, reason = detect_role()
    return reason == ".jejune/role"



def _graph_available() -> bool:
    from .graph import graph_available
    ok, _ = graph_available()
    return ok


def _graph_extract_command() -> str:
    from .neo4j import db_is_empty
    cmd = "jejune graph extract"
    if not db_is_empty():
        cmd += " (warning: database is not empty)"
    return cmd


def _neo4j_running() -> bool:
    from .neo4j import container_running
    ok, _ = container_running()
    return ok


def _neo4j_not_empty() -> bool:
    from .neo4j import db_is_empty
    return not db_is_empty()


def _neo4j_configured() -> bool:
    from .configuration import component_config_check
    status, _ = component_config_check("neo4j")
    return status == "ok"


def _manifest_ok() -> bool:
    from pathlib import Path
    from .test import _check_doc_yaml
    errors, _ = _check_doc_yaml(Path.cwd())
    return not errors


def _is_catalog_installed() -> bool:
    try:
        from jejune_catalog._commands import _load_catalog_docs
        from .ecosystem import repo_status, resolve_dirs
    except ImportError:
        return True  # catalog plugin absent — nothing to install
    try:
        docs = _load_catalog_docs(None)
    except Exception:
        return True  # no catalog.yaml → nothing to install
    try:
        eco_root, eco_tmp = resolve_dirs()
        return all(
            repo_status(doc["name"], eco_root, eco_tmp)[0] in ("root", "tmp")
            for doc in docs
        )
    except Exception:
        return False


def _is_deployment_installed() -> bool:
    from .deployer_extensions import _extensions_installed
    return _is_catalog_installed() and _extensions_installed()


def _is_catalog_contributor_cwd() -> bool:
    """True when role is catalog-contributor, cwd is a git clone, and the repo is jejune_catalog."""
    import subprocess
    from pathlib import Path
    from .role import detect_role
    role, _ = detect_role()
    if role != "catalog-contributor":
        return False
    if not (Path.cwd() / ".git").exists():
        return False
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=Path.cwd(), stderr=subprocess.DEVNULL, text=True,
        ).strip()
        return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git") == "jejune_catalog"
    except Exception:
        return False


def _is_jejune_workspace_cwd() -> bool:
    from .ui_deployment import _is_deployer_cwd
    return _is_document_cwd() or _is_deployer_cwd() or _is_catalog_contributor_cwd()


def _is_document_cwd() -> bool:
    """True when the role is doc-steward and catalog.yaml exists in cwd."""
    from pathlib import Path
    from .role import detect_role
    role, _ = detect_role()
    return role == "doc-steward" and (Path.cwd() / "catalog.yaml").is_file()


# ---------------------------------------------------------------------------
# Registration — called from main.py after plugins are loaded so ROLES is
# complete (plugins may register additional roles).
# ---------------------------------------------------------------------------

def register_heuristics() -> None:
    """Register all CLI heuristics. Must be called after _load_plugins()."""
    register_precondition("role set", _is_role_set)
    register_precondition("deployment installed", _is_deployment_installed)

    register_command_precondition("jejune neo4j dump-turtle", _neo4j_running)
    register_command_precondition("jejune graph split", _manifest_ok)

    register_heuristic(HeuristicStep(
        label="Connect to a jejune workspace directory",
        command="cd <jejune_doc_or_deploy_dir>",
        anti_conditions=[_is_jejune_workspace_cwd],
    ), roles={None})

    register_heuristic(HeuristicStep(
        label="Create document workspace directory",
        command="jejune document init --help",
        anti_conditions=[_is_jejune_workspace_cwd],
    ), roles={None})

    register_heuristic(HeuristicStep(
        label="Create deployment workspace directory",
        command="jejune deployment init --help",
        anti_conditions=[_is_jejune_workspace_cwd],
    ), roles={None})

    from .ui_deployment import _is_deployer_cwd
    register_heuristic(HeuristicStep(
        label="Install deployment",
        command="jejune deployment install",
        conditions=[_is_deployer_cwd],
        anti_conditions=[_is_deployment_installed],
    ), roles={"deployer"})

    register_heuristic(HeuristicStep(
        label="Start Neo4j",
        command="jejune neo4j start --help",
        order=10,
        conditions=[_neo4j_configured],
        anti_conditions=[_neo4j_running],
    ), roles={"doc-steward"})

    register_heuristic(HeuristicStep(
        label="Extract the knowledge graph",
        command=_graph_extract_command,
        conditions=[_graph_available],
        anti_conditions=[_neo4j_not_empty],
    ), roles={"doc-steward"})

    register_heuristic(HeuristicStep(
        label="Dump the graph to Turtle",
        command="jejune neo4j dump-turtle",
        conditions=[_neo4j_running, _neo4j_not_empty],
    ), roles={"doc-steward"})

    register_heuristic(HeuristicStep(
        label="Visualize the graph with neo4j UI",
        command="open http://localhost:7474 in a browser",
        conditions=[_neo4j_running, _neo4j_not_empty],
    ), roles={"doc-steward"})
