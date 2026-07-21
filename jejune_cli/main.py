import importlib.metadata

import click

from ._env import dot_jejune, load_env_files
from .catalog import catalog, run_all
from .plugin import JejunePlugin, _REGISTRY
from .deployment import deployment
from .configuration import (
    configuration,
    COMPONENT_CONFIG_HINTS as _CONFIG_HINTS,
    get_config_hint,
)
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
# Frozen at startup — used to distinguish built-ins from loaded plugins in help.
_BUILTIN_COMPONENTS: frozenset[str] = frozenset(_COMPONENTS)


_W_SECT = 17  # len("llm-observability") — recomputed after _load_plugins()
_W_MSG = 16  # "not configured" = 14

_STATUS_RANK = {"error": 2, "warn": 1, "ok": 0}
_STATUS_LABEL = {"ok": "ok", "warn": "not configured", "error": "error"}


_AVAIL_HINTS: dict[str, str] = {
    "neo4j": "run `jejune neo4j start --help`",
    "llm": "run `jejune llm status`",
    "llm-observability": "run `jejune llm-observability start`",
}

# Required dependencies: a component is only effective when all its deps are ok.
_COMPONENT_DEPS: dict[str, list[str]] = {
    "graph": ["neo4j", "llm"],
    "deployment": ["catalog"],
    "pdf-to-markdown": ["catalog"],
}

# Optional dependencies: enhance a component but do not affect its effective status.
_COMPONENT_OPTIONAL_DEPS: dict[str, list[str]] = {
    "graph": ["llm-observability"],
}


class _JejuneGroup(click.Group):
    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        formatter.write_usage(ctx.command_path, "[OPTIONS] COMPONENT COMMAND [ARGS]...")

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        # Built-in components are described in the docstring above; plugins get
        # their own section; only truly uncovered commands fall through here.
        covered = _BUILTIN_COMPONENTS | {"configuration"} | {p.name for p in _REGISTRY}
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
        _STAGE_TITLES = {
            "single-document": "Single-document extension components",
            "collection": "Collection-level extension components",
            "extension": "Extension components",
        }
        by_stage: dict[str, list] = {}
        for p in _REGISTRY:
            by_stage.setdefault(p.stage, []).append(p)
        for stage in ("single-document", "collection", "extension"):
            if stage not in by_stage:
                continue
            with formatter.section(_STAGE_TITLES[stage]):
                formatter.write_dl([
                    (p.name, p.group.get_short_help_str(limit=formatter.width))
                    for p in by_stage[stage]
                ])


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
        click.echo(
            click.style(
                f"No .jejune/ directory found in {d.parent}.\n"
                "Run `jejune configuration init` first to set up the workspace.",
                fg="yellow",
            )
        )
        raise SystemExit(1)

    config_results, avail_results = run_all()
    by_config = {comp: (status, msg) for comp, status, msg in config_results}
    by_avail = {comp: (status, msg) for comp, status, msg in avail_results}

    # Ensure every component appears in the config table, in _COMPONENTS order.
    config_results = [
        (comp,) + by_config.get(comp, ("ok", "ok")) for comp in _COMPONENTS
    ]

    failed_config: list[str] = []
    failed_avail: list[str] = []

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
    _W_HINT = max(len("Hint"), max(len(h) for h in _CONFIG_HINTS.values()))
    _W_DIAG_HINT = max(
        len("Diagnostic hint"), max(len(h) for h in _AVAIL_HINTS.values())
    )
    _W_DEPENDS = max(len("Depends on"), max(len(_deps_str(c)) for c in _COMPONENT_DEPS))
    sep = max(
        len(_CONFIG_NOTE),
        2 + _W_SECT + 1 + _W_MSG + 1 + _W_HINT,
        2 + _W_SECT + 1 + _W_MSG + 1 + _W_DIAG_HINT,
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

    def _deps_colored(comp: str) -> str:
        req = _COMPONENT_DEPS.get(comp, [])
        opt = _COMPONENT_OPTIONAL_DEPS.get(comp, [])
        req_parts = [
            click.style(dep, fg="green" if _comp_status(dep) == "ok" else "red")
            for dep in req
        ]
        result = ", ".join(req_parts)
        if opt:
            opt_parts = [
                click.style(dep, fg="green" if _comp_status(dep) == "ok" else "yellow")
                for dep in opt
            ]
            result += f" ({', '.join(opt_parts)} optional)"
        return result

    click.echo("jejune COMPONENT COMMAND [ARGS]")
    click.echo("=" * sep)
    click.echo(_CONFIG_NOTE)
    click.echo()

    # ── Configuration ────────────────────────────────────────────────
    click.echo(f"  {'Configuration':<{_W_SECT}} {'Status':<{_W_MSG}} Hint")
    click.echo(divider)
    for comp, status, msg in config_results:
        if status == "error":
            failed_config.append(comp)
        hint = "" if status == "ok" else get_config_hint(comp, status, msg)
        click.echo(f"  {comp:<{_W_SECT}} {_config_label(status)} {hint}")
    click.echo()

    # ── Availability ─────────────────────────────────────────────────
    click.echo(f"  {'Availability':<{_W_SECT}} {'Status':<{_W_MSG}} Diagnostic hint")
    click.echo(divider)
    for comp, status, msg in avail_results:
        if status == "error":
            failed_avail.append(comp)
        if msg == "not configured":
            hint = "Refer above to configuration hint"
        elif status == "error":
            hint = _AVAIL_HINTS.get(comp, msg)
        elif msg == "not started":
            hint = _AVAIL_HINTS.get(comp, "")
        else:
            hint = ""
        click.echo(f"  {comp:<{_W_SECT}} {_avail_label(status, msg)} {hint}")
    click.echo()

    # ── Components ───────────────────────────────────────────────────
    click.echo(f"  {'Component':<{_W_SECT}} {'Effective':<{_W_MSG}} Depends on")
    click.echo(divider)
    for comp in _COMPONENT_DEPS:
        click.echo(
            f"  {comp:<{_W_SECT}} {_config_label(_effective_status(comp))} {_deps_colored(comp)}"
        )

    # ── Summary ──────────────────────────────────────────────────────
    click.echo("=" * sep)
    if not failed_config and not failed_avail:
        click.echo(click.style("Your jejune workspace looks healthy.", fg="green"))
    else:
        if failed_config:
            click.echo(click.style("Configuration issues:", fg="red"))
            click.echo()
            _W = max(len(n) for n in failed_config)
            _WH = max(
                len(get_config_hint(n, "error", by_config[n][1])) for n in failed_config
            )
            for name in failed_config:
                detail = by_config[name][1]
                action = get_config_hint(name, "error", detail)
                click.echo(
                    f"  {click.style(f'{name:<{_W}}', fg='red')}  {action:<{_WH}}  [{detail}]"
                )
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
                click.echo(
                    f"  {click.style(f'{name:<{_W}}', fg='red')}  {action:<{_WH}}  [{detail}]"
                )


cli.add_command(configuration)
cli.add_command(neo4j)
cli.add_command(llm)
cli.add_command(llm_observability)
cli.add_command(graph)
cli.add_command(catalog)
cli.add_command(deployment)
cli.add_command(pdf_to_markdown)
cli.add_command(doctor)


def _load_plugins() -> None:
    global _W_SECT
    from .configuration import CONFIG_GROUPS, COMPONENT_CONFIG_HINTS
    for ep in importlib.metadata.entry_points(group="jejune.plugins"):
        try:
            plugin: JejunePlugin = ep.load()
        except Exception as exc:
            click.echo(f"Warning: failed to load plugin {ep.name!r}: {exc}", err=True)
            continue
        _REGISTRY.append(plugin)
        cli.add_command(plugin.group, plugin.name)
        _COMPONENTS.append(plugin.name)
        if plugin.required_deps:
            _COMPONENT_DEPS[plugin.name] = plugin.required_deps
        if plugin.optional_deps:
            _COMPONENT_OPTIONAL_DEPS[plugin.name] = plugin.optional_deps
        if plugin.avail_hint:
            _AVAIL_HINTS[plugin.name] = plugin.avail_hint
        if plugin.config_vars:
            CONFIG_GROUPS[plugin.name] = (plugin.config_vars, plugin.name)
            COMPONENT_CONFIG_HINTS[plugin.name] = plugin.config_hint
    _W_SECT = max(len(n) for n in _COMPONENTS)


_load_plugins()
