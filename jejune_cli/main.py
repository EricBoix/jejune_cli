import click

from ._env import dot_jejune, load_env_files
from .catalog import catalog, run_all
from .deployment import deployment
from .env import env
from .graph import graph
from .llm_observability import llm_observability
from .neo4j import neo4j
from .pdf_to_markdown import pdf_to_markdown

_W_SECT = 17   # len("llm-observability")
_W_MSG  = 16   # "not configured" = 14

_STATUS_RANK  = {"error": 2, "warn": 1, "ok": 0}
_STATUS_LABEL = {"ok": "ok", "warn": "not configured", "error": "error"}

# Component → commands it enables.
_COMPONENT_ENABLES: dict[str, str] = {
    "neo4j":             "neo4j *, graph dump-turtle, graph extract",
    "llm":               "graph extract",
    "llm-observability": "graph extract (LLM tracing)",
    "workspace":         "pdf-to-markdown test, catalog check",
    "catalog":           "pdf-to-markdown test, catalog check",
}

_CONFIG_HINTS: dict[str, str] = {
    "neo4j":     "edit .jejune/env-secrets",
    "llm":       "edit .jejune/env-secrets",
    "workspace": "edit .jejune/env-config",
    "catalog":   "run `jejune catalog check`",
}

_AVAIL_HINTS: dict[str, str] = {
    "neo4j":             "run `jejune neo4j start`",
    "llm":               "check LLM server connectivity",
    "llm-observability": "run `jejune llm-observability start`",
}


@click.group()
def cli():
    """jejune — jejuneness workflow CLI.

    Single-document commands (operate on one jj_doc_* repository):\n
      jejune env      Manage the local .jejune/ environment\n
      jejune neo4j    Manage the Neo4j instance\n
      jejune graph    Build and export the knowledge graph\n

    Collection-level commands (operate across a catalog of repositories):\n
      jejune catalog        Manage the document catalog\n
      jejune deployment     Manage deployments\n
      jejune pdf-to-markdown  Test the pipeline across the catalog\n

    Run `jejune env init` first in a repository, then `jejune doctor`.
    """
    load_env_files()


@cli.command()
def doctor():
    """Report component configuration and availability. Inspired by `brew doctor`.

    Two-stage check:\n
      Configuration — were the components configured by the user?\n
      Availability  — are the component services reachable?\n

    Followed by a Components summary showing which commands each enables.
    """
    d = dot_jejune()
    if not d.is_dir():
        click.echo(click.style(
            f"No .jejune/ directory found in {d.parent}.\n"
            "Run `jejune env init` first to set up the workspace.",
            fg="yellow",
        ))
        raise SystemExit(1)

    config_results, avail_results = run_all()
    by_config = {comp: (status, msg) for comp, status, msg in config_results}
    by_avail  = {comp: (status, msg) for comp, status, msg in avail_results}

    failed_config: list[str] = []
    failed_avail:  list[str] = []

    _CONFIG_NOTE = (
        "  Config: .jejune/env-config · .jejune/env-secrets · .jejune/catalog.yaml"
    )
    _W_ENABLES = max(len(e) for e in _COMPONENT_ENABLES.values())
    sep = max(
        len(_CONFIG_NOTE),
        2 + _W_SECT + 1 + _W_MSG + 1 + _W_ENABLES,
    )
    divider = "  " + "─" * (sep - 2)

    def _config_label(status: str) -> str:
        text = _STATUS_LABEL[status]
        fg = {"ok": "green", "warn": "yellow", "error": "red"}[status]
        return click.style(f"{text:<{_W_MSG}}", fg=fg)

    def _avail_label(status: str, msg: str) -> str:
        text = "error" if status == "error" else msg
        fg = {"ok": "green", "warn": "yellow", "error": "red"}[status]
        return click.style(f"{text:<{_W_MSG}}", fg=fg)

    def _comp_status(comp: str) -> str:
        cs = by_config.get(comp, ("ok", ""))[0]
        av = by_avail.get(comp, ("ok", ""))[0]
        return max(cs, av, key=lambda s: _STATUS_RANK.get(s, 0))

    click.echo("jejune COMPONENT COMMAND [ARGS]")
    click.echo("=" * sep)
    click.echo(_CONFIG_NOTE)
    click.echo()

    # ── Configuration ────────────────────────────────────────────────
    click.echo(f"  {'Configuration':<{_W_SECT}} {'Status':<{_W_MSG}}")
    click.echo(divider)
    for comp, status, _ in config_results:
        if status == "error":
            failed_config.append(comp)
        click.echo(f"  {comp:<{_W_SECT}} {_config_label(status)}")
    click.echo()

    # ── Availability ─────────────────────────────────────────────────
    click.echo(f"  {'Availability':<{_W_SECT}} {'Status':<{_W_MSG}}")
    click.echo(divider)
    for comp, status, msg in avail_results:
        if status == "error":
            failed_avail.append(comp)
        click.echo(f"  {comp:<{_W_SECT}} {_avail_label(status, msg)}")
    click.echo()

    # ── Components ───────────────────────────────────────────────────
    click.echo(f"  {'Component':<{_W_SECT}} {'Status':<{_W_MSG}} Enables")
    click.echo(divider)
    for comp, enables in _COMPONENT_ENABLES.items():
        click.echo(f"  {comp:<{_W_SECT}} {_config_label(_comp_status(comp))} {enables}")

    # ── Summary ──────────────────────────────────────────────────────
    click.echo("=" * sep)
    if not failed_config and not failed_avail:
        click.echo(click.style("Your jejune workspace looks healthy.", fg="green"))
    else:
        if failed_config:
            click.echo(click.style("Configuration issues:", fg="red"))
            click.echo()
            _W = max(len(n) for n in failed_config)
            _WH = max(len(_CONFIG_HINTS.get(n, "investigate")) for n in failed_config)
            for name in failed_config:
                action = _CONFIG_HINTS.get(name, "investigate")
                detail = by_config[name][1]
                click.echo(f"  {click.style(f'{name:<{_W}}', fg='red')}  {action:<{_WH}}  [{detail}]")
        if failed_avail:
            if failed_config:
                click.echo()
            click.echo(click.style("Availability issues:", fg="red"))
            click.echo()
            _W = max(len(n) for n in failed_avail)
            _WH = max(len(_AVAIL_HINTS.get(n, "investigate")) for n in failed_avail)
            for name in failed_avail:
                action = _AVAIL_HINTS.get(name, "investigate")
                detail = by_avail[name][1]
                click.echo(f"  {click.style(f'{name:<{_W}}', fg='red')}  {action:<{_WH}}  [{detail}]")


cli.add_command(env)
cli.add_command(neo4j)
cli.add_command(graph)
cli.add_command(llm_observability)
cli.add_command(catalog)
cli.add_command(deployment)
cli.add_command(pdf_to_markdown)
cli.add_command(doctor)
