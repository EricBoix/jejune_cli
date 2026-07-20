import click

from ._env import dot_jejune, load_env_files
from .catalog import catalog, run_all
from .deployment import deployment
from .configuration import configuration
from .graph import graph
from .llm import llm
from .llm_observability import llm_observability
from .neo4j import neo4j
from .pdf_to_markdown import pdf_to_markdown

# Components — drives both `jejune --help` listing and `jejune doctor` output.
# env is a CLI command but not a component.
_COMPONENTS = [
    "neo4j",
    "llm",
    "llm-observability",
    "graph",
    "catalog",
    "deployment",
    "pdf-to-markdown",
]


_W_SECT = 17   # len("llm-observability")
_W_MSG  = 16   # "not configured" = 14

_STATUS_RANK  = {"error": 2, "warn": 1, "ok": 0}
_STATUS_LABEL = {"ok": "ok", "warn": "not configured", "error": "error"}

_CONFIG_HINTS: dict[str, str] = {
    "neo4j":   "edit .jejune/env-secrets",
    "llm":     "edit .jejune/env-secrets",
    "catalog": "run `jejune catalog check`",
}

_AVAIL_HINTS: dict[str, str] = {
    "neo4j":             "run `jejune neo4j start`",
    "llm":               "check LLM server connectivity",
    "llm-observability": "run `jejune llm-observability start`",
}

# Required dependencies: a component is only effective when all its deps are ok.
_COMPONENT_DEPS: dict[str, list[str]] = {
    "graph":           ["neo4j", "llm"],
    "deployment":      ["catalog"],
    "pdf-to-markdown": ["catalog"],
}

# Optional dependencies: enhance a component but do not affect its effective status.
_COMPONENT_OPTIONAL_DEPS: dict[str, list[str]] = {
    "graph": ["llm-observability"],
}


class _JejuneGroup(click.Group):
    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        formatter.write_usage(ctx.command_path, "[OPTIONS] COMPONENT COMMAND [ARGS]...")

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        # Components and shared commands are described in the docstring above;
        # only emit commands not covered there.
        covered = set(_COMPONENTS) | {"configuration"}
        rows: list[tuple[str, str]] = []
        for name in self.list_commands(ctx):
            if name in covered:
                continue
            cmd = self.get_command(ctx, name)
            if cmd is None or cmd.hidden:
                continue
            rows.append((name, cmd.get_short_help_str(limit=formatter.width)))
        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


@click.group(cls=_JejuneGroup)
def cli():
    """jejune — jejuneness workflow CLI.

    \b
    Shared (single-document and collection-level):
      jejune configuration     Manage the .jejune/ configuration
      Run `jejune configuration init` first — in a jj_doc_<name> repository
      for single-document use, or a deployment directory for collection-level.

    \b
    Single-document commands (jj_doc_<name> repository):
      jejune neo4j              Manage the Neo4j instance
      jejune llm                Manage the LLM inference server
      jejune llm-observability  Manage the LLM observability backend
      jejune graph              Build and export the knowledge graph

    \b
    Collection-level commands (catalog of repositories):
      jejune catalog            Manage the document catalog
      jejune deployment         Manage deployments
      jejune pdf-to-markdown    Test the pipeline across the catalog
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
            "Run `jejune configuration init` first to set up the workspace.",
            fg="yellow",
        ))
        raise SystemExit(1)

    config_results, avail_results = run_all()
    by_config = {comp: (status, msg) for comp, status, msg in config_results}
    by_avail  = {comp: (status, msg) for comp, status, msg in avail_results}

    failed_config: list[str] = []
    failed_avail:  list[str] = []

    def _deps_str(comp: str) -> str:
        req = _COMPONENT_DEPS.get(comp, [])
        opt = _COMPONENT_OPTIONAL_DEPS.get(comp, [])
        result = ", ".join(req)
        if opt:
            result += f" ({', '.join(opt)} optional)"
        return result

    _CONFIG_NOTE = (
        "  Config: .jejune/env-config · .jejune/env-secrets · .jejune/catalog.yaml"
    )
    _W_DEPENDS = max(len("Depends on"), max(len(_deps_str(c)) for c in _COMPONENT_DEPS))
    sep = max(
        len(_CONFIG_NOTE),
        2 + _W_SECT + 1 + _W_MSG + 1 + _W_DEPENDS,
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

    def _effective_status(comp: str) -> str:
        statuses = [_comp_status(comp)] + [
            _comp_status(dep) for dep in _COMPONENT_DEPS.get(comp, [])
        ]
        return max(statuses, key=lambda s: _STATUS_RANK.get(s, 0))

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
    click.echo(f"  {'Component':<{_W_SECT}} {'Effective':<{_W_MSG}} Depends on")
    click.echo(divider)
    for comp in _COMPONENT_DEPS:
        click.echo(f"  {comp:<{_W_SECT}} {_config_label(_effective_status(comp))} {_deps_str(comp)}")

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


cli.add_command(configuration)
cli.add_command(neo4j)
cli.add_command(llm)
cli.add_command(llm_observability)
cli.add_command(graph)
cli.add_command(catalog)
cli.add_command(deployment)
cli.add_command(pdf_to_markdown)
cli.add_command(doctor)
