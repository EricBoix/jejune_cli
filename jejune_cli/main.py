import importlib.metadata
import subprocess
from pathlib import Path

import click

from ._env import dot_jejune, load_env_files
from .catalog import run_all
from .convert import convert, convert_configured
from .plugin import JejunePlugin, _REGISTRY
from .deployment import deployment
from .configuration import (
    configuration,
    COMPONENT_CONFIG_HINTS as _CONFIG_HINTS,
    get_config_hint,
)
from . import containers
from .containers import containers_cli
from .graph import graph
from .llm import llm
from .llm_observability import llm_observability
from .neo4j import neo4j
from .pdf_to_markdown import pdf_to_markdown
from .role import detect_role, role_components

_ACTIVE_ROLE, _ACTIVE_ROLE_REASON = detect_role()
_ACTIVE_COMPONENTS = role_components(_ACTIVE_ROLE)

# Components — drives both `jejune --help` listing and `jejune doctor` output.
_COMPONENTS = [
    "neo4j",
    "llm",
    "llm-observability",
    "graph",
    "deployment",
    "pdf-to-markdown",
    "convert",
]
# Frozen at startup — used to distinguish built-ins from loaded plugins in help.
_BUILTIN_COMPONENTS: frozenset[str] = frozenset(_COMPONENTS)

# Help-section membership for built-in components.
_ALL_ROLES_COMMANDS = ["doctor", "init", "role", "containers"]
_DOC_STEWARD_COMPONENTS = ["configuration", "neo4j", "llm", "llm-observability", "graph", "convert"]
_CURATOR_COMPONENTS = ["pdf-to-markdown"]   # + "collection" stage plugins
_DEPLOYER_COMPONENTS = ["deployment"]       # + "extension" stage plugins


_W_SECT = 17  # len("llm-observability") — recomputed after _load_plugins()
_W_MSG = 16  # "not configured" = 14

_STATUS_RANK = {"error": 2, "warn": 1, "ok": 0}
_STATUS_LABEL = {"ok": "ok", "warn": "not configured", "error": "error"}


_AVAIL_HINTS: dict[str, str] = {
    "neo4j": "run `jejune neo4j start --help`",
    "llm": "run `jejune llm status`",
    "llm-observability": "run `jejune llm-observability start`",
    "convert": "run `jejune convert build`",
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


def _is_visible(name: str) -> bool:
    """True when name should appear for the active role."""
    return _ACTIVE_COMPONENTS is None or name in _ACTIVE_COMPONENTS


class _JejuneGroup(click.Group):
    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        formatter.write_usage(ctx.command_path, "[OPTIONS] COMPONENT COMMAND [ARGS]...")

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        load_env_files()  # ensure .jejune/env-config is loaded for conditional visibility

        _hidden_unless_configured = {
            "convert": convert_configured,
        }

        def _row(name: str) -> tuple[str, str] | None:
            guard = _hidden_unless_configured.get(name)
            if guard is not None and not guard():
                return None
            cmd = self.get_command(ctx, name)
            if cmd and not cmd.hidden:
                return (f"jejune {name}", cmd.get_short_help_str(limit=formatter.width))
            return None

        def _rows(names: list[str]) -> list[tuple[str, str]]:
            return [r for name in names if (r := _row(name))]

        def _plugin_rows(stage: str) -> list[tuple[str, str]]:
            return [
                (f"jejune {p.name}", p.group.get_short_help_str(limit=formatter.width))
                for p in _REGISTRY if p.stage == stage
            ]

        # All sections always shown — section titles communicate the role.
        all_roles = [r for name in _ALL_ROLES_COMMANDS if (r := _row(name))]
        if all_roles:
            with formatter.section("For all roles"):
                formatter.write_dl(all_roles)

        doc_steward = _rows(_DOC_STEWARD_COMPONENTS) + _plugin_rows("single-document")
        if doc_steward:
            with formatter.section("Doc-steward commands"):
                formatter.write_dl(doc_steward)

        curator = _rows(_CURATOR_COMPONENTS) + _plugin_rows("collection")
        if curator:
            with formatter.section("Catalog Curator commands"):
                formatter.write_dl(curator)

        deployer = _rows(_DEPLOYER_COMPONENTS) + _plugin_rows("extension")
        if deployer:
            with formatter.section("Deployer commands"):
                formatter.write_dl(deployer)


def _version_string() -> str:
    version = importlib.metadata.version("jejune-cli")
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").is_dir():
            try:
                sha = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True, check=True,
                    cwd=candidate,
                ).stdout.strip()
                if sha:
                    return f"{version} ({sha})"
            except Exception:
                pass
            break
    try:
        from ._sha import SHA
        if SHA:
            return f"{version} ({SHA})"
    except ImportError:
        pass
    return version


@click.group(cls=_JejuneGroup)
@click.version_option(version=_version_string(), prog_name="jejune")
def cli():
    """jejune — jejuneness workflow CLI.

    Run `jejune init` first in your working directory to set up the workspace.
    """
    load_env_files()


@cli.command()
def role():
    """Show the detected role and the reason for it.

    Role is inferred from the current directory. Override with JEJUNE_ROLE env var.
    """
    if _ACTIVE_ROLE:
        click.echo(f"role:   {click.style(_ACTIVE_ROLE, fg='cyan')}")
    else:
        click.echo(f"role:   {click.style('(none)', fg='yellow')}")
    click.echo(f"reason: {_ACTIVE_ROLE_REASON}")
    if _ACTIVE_COMPONENTS:
        click.echo(f"shows:  {', '.join(sorted(_ACTIVE_COMPONENTS))}")
    else:
        click.echo("shows:  all components")


@cli.command()
@click.argument("name", required=False)
def init(name):
    """Initialize the workspace for the detected role.

    \b
    doc-steward    : creates .jejune/ scaffold (NAME ignored)
    deployer       : scaffolds a deployment directory named NAME
    catalog-curator: not yet implemented
    (no role)      : creates .jejune/ scaffold
    """
    from .configuration import init as _steward_init
    from .ui_deployment import ui_configure

    if _ACTIVE_ROLE == "deployer":
        if not name:
            raise click.UsageError("NAME is required for the deployer role.")
        ui_configure.invoke(click.get_current_context(), deployments_dir=".", name=name)
    elif _ACTIVE_ROLE == "catalog-curator":
        click.echo(click.style("Catalog Curator init: not yet implemented.", fg="yellow"))
    else:
        ctx = click.get_current_context()
        ctx.invoke(_steward_init)


@cli.command()
def doctor():
    """Report component configuration and availability. Inspired by `brew doctor`.

    Two-stage check:\n
      Configuration — were the components configured by the user?\n
      Availability  — are the component services reachable?\n

    Followed by a Components summary showing which commands each enables.
    Only components relevant to the detected role are shown.
    """
    d = dot_jejune()
    if _ACTIVE_ROLE in (None, "doc-steward") and not d.is_dir():
        click.echo(
            click.style(
                f"No .jejune/ directory found in {d.parent}.\n"
                "Run `jejune init` first to set up the workspace.",
                fg="yellow",
            )
        )
        raise SystemExit(1)

    config_results, avail_results = run_all(components=_ACTIVE_COMPONENTS)
    by_config = {comp: (status, msg) for comp, status, msg in config_results}
    by_avail = {comp: (status, msg) for comp, status, msg in avail_results}

    visible_components = [c for c in _COMPONENTS if _is_visible(c)]  # doctor stays role-scoped
    for p in _REGISTRY:
        if _is_visible(p.name) and p.name not in visible_components:
            visible_components.append(p.name)

    config_results = [
        (comp,) + by_config.get(comp, ("ok", "ok")) for comp in visible_components
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

    all_hints = list(_CONFIG_HINTS.values()) or [""]
    all_avail_hints = list(_AVAIL_HINTS.values()) or [""]
    all_deps = [_deps_str(c) for c in _COMPONENT_DEPS] or [""]

    _CONFIG_NOTE = (
        "  Configuration files: .jejune/env-config · .jejune/env-secrets · .jejune/catalog.yaml"
    )
    _W_HINT = max(len("Hint"), max(len(h) for h in all_hints))
    _W_DIAG_HINT = max(len("Diagnostic hint"), max(len(h) for h in all_avail_hints))
    _W_DEPENDS = max(len("Depends on"), max(len(d) for d in all_deps))
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

    role_label = f" [{_ACTIVE_ROLE}]" if _ACTIVE_ROLE else ""
    click.echo(f"jejune doctor{role_label}")
    click.echo("=" * sep)
    click.echo()

    # ── Configuration ────────────────────────────────────────────────
    if _ACTIVE_ROLE in (None, "doc-steward"):
        click.echo(_CONFIG_NOTE)
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
        elif msg in ("not started", "not built"):
            hint = _AVAIL_HINTS.get(comp, "")
        else:
            hint = ""
        click.echo(f"  {comp:<{_W_SECT}} {_avail_label(status, msg)} {hint}")
    click.echo()

    # ── Components ───────────────────────────────────────────────────
    visible_deps = {c: deps for c, deps in _COMPONENT_DEPS.items() if _is_visible(c)}
    if visible_deps:
        click.echo(f"  {'Component':<{_W_SECT}} {'Effective':<{_W_MSG}} Depends on")
        click.echo(divider)
        for comp in visible_deps:
            click.echo(
                f"  {comp:<{_W_SECT}} {_config_label(_effective_status(comp))} {_deps_colored(comp)}"
            )

    # ── Containers ───────────────────────────────────────────────────
    click.echo("=" * sep)
    containers.print_containers_table()
    click.echo()

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
cli.add_command(containers_cli)
cli.add_command(neo4j)
cli.add_command(llm)
cli.add_command(llm_observability)
cli.add_command(graph)
cli.add_command(deployment)
cli.add_command(pdf_to_markdown)
cli.add_command(convert)
cli.add_command(doctor)
cli.add_command(role)
cli.add_command(init)


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
