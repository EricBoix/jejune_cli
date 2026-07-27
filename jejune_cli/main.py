import importlib.metadata
import subprocess
from pathlib import Path

import click

from ._env import dot_jejune, load_env_files
from .catalog import run_all
from .convert import convert, convert_configured
from .plugin import JejunePlugin, _REGISTRY
from .deployment import deployment
from .ui_deployment import build
from .configuration import (
    configuration,
    COMPONENT_CONFIG_HINTS as _CONFIG_HINTS,
    get_config_hint,
    print_config_table,
    print_two_col_table,
)
from . import containers
from .containers import containers_cli
from .graph import graph
from .llm import llm
from .llm_observability import llm_observability
from .neo4j import neo4j
from .test import test_cmd
from .role import detect_role, role_components, ROLES, ROLE_SECTION_TITLE

_ACTIVE_ROLE, _ACTIVE_ROLE_REASON = detect_role()
_ACTIVE_COMPONENTS = role_components(_ACTIVE_ROLE)

# Components — drives both `jejune --help` listing and `jejune doctor` output.
_COMPONENTS = [
    "neo4j",
    "llm",
    "llm-observability",
    "graph",
    "deployment",
    "test",
    "convert",
]
# Frozen at startup — used to distinguish built-ins from loaded plugins in help.
_BUILTIN_COMPONENTS: frozenset[str] = frozenset(_COMPONENTS)

# Help-section membership for built-in components.
_ALL_ROLES_COMMANDS = ["doctor", "configuration", "role", "containers"]
_DOC_STEWARD_COMPONENTS = ["neo4j", "llm", "llm-observability", "graph", "convert"]
_CURATOR_COMPONENTS = ["test"]   # + "collection" stage plugins
_DEPLOYER_COMPONENTS = ["deployment", "build"]  # + "extension" stage plugins

# Ordered sections for `jejune --help`, keyed by role name from ROLE_SECTION_TITLE.
_ROLE_HELP_SECTIONS: list[tuple[str, list[str], str | None]] = [
    ("all",             _ALL_ROLES_COMMANDS,     None),
    ("doc-steward",     _DOC_STEWARD_COMPONENTS, "single-document"),
    ("catalog-curator", _CURATOR_COMPONENTS,     "collection"),
    ("deployer",        _DEPLOYER_COMPONENTS,    "extension"),
]


_W_SECT = max(17, len("Component configuration"))  # recomputed after _load_plugins()
_W_MSG = 16  # "not configured" = 14

_STATUS_RANK = {"error": 2, "warn": 1, "ok": 0}
_STATUS_FG = {"ok": "green", "warn": "yellow", "error": "red"}


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
    "test": ["catalog"],
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
        prefix = f"Usage [{_ACTIVE_ROLE}]: " if _ACTIVE_ROLE in ROLES else "Usage: "
        formatter.write_usage(ctx.command_path, "[OPTIONS] COMPONENT COMMAND [ARGS]...", prefix=prefix)

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

        for role_name, commands, plugin_stage in _ROLE_HELP_SECTIONS:
            if _ACTIVE_ROLE in ROLES and role_name not in ("all", _ACTIVE_ROLE):
                continue
            rows = _rows(commands)
            if plugin_stage:
                rows += _plugin_rows(plugin_stage)
            if rows:
                with formatter.section(ROLE_SECTION_TITLE[role_name]):
                    formatter.write_dl(rows)


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

    Run `jejune configuration <role> init` to set up a new workspace.
    """
    load_env_files()


@click.group(invoke_without_command=True, short_help="Show or list roles")
@click.pass_context
def role(ctx):
    """Show the detected role, or use a subcommand.

    Role is inferred from the current directory. Override with JEJUNE_ROLE env var.
    """
    if ctx.invoked_subcommand is not None:
        return
    if _ACTIVE_ROLE:
        click.echo(f"role:   {click.style(_ACTIVE_ROLE, fg='cyan')}")
    else:
        click.echo(f"role:   {click.style('(none)', fg='yellow')}")
    click.echo(f"reason: {_ACTIVE_ROLE_REASON}")
    if _ACTIVE_COMPONENTS:
        click.echo(f"shows:  {', '.join(sorted(_ACTIVE_COMPONENTS))}")
    else:
        click.echo("shows:  all components")


@role.command("list")
def role_list():
    """List all known roles with their detection indicator."""
    from .role import _DISPLAY_ROLES, _ROLE_REASON
    _W = max(len(r) for r in _DISPLAY_ROLES)
    for r in _DISPLAY_ROLES:
        click.echo(f"  {r:<{_W}}  {_ROLE_REASON.get(r, '')}")



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
                "Run `jejune configuration doc-steward init` to set up the workspace.",
                fg="yellow",
            )
        )
        raise SystemExit(1)

    config_results, avail_results = run_all(components=_ACTIVE_COMPONENTS)
    by_config = {comp: (status, msg) for comp, status, msg in config_results}
    by_avail = {comp: (status, msg) for comp, status, msg in avail_results}

    visible_components = [c for c in _COMPONENTS if _is_visible(c)]
    for p in _REGISTRY:
        if _is_visible(p.name) and p.name not in visible_components:
            visible_components.append(p.name)

    config_rows: list[tuple[str, str, str, str]] = [
        (comp, status, msg if status == "error" else "", "" if status == "ok" else get_config_hint(comp, status, msg))
        for comp, (status, msg) in [
            (c, by_config.get(c, ("ok", "ok"))) for c in visible_components
        ]
    ]
    failed_config = [comp for comp, status, _, _ in config_rows if status == "error"]

    avail_rows = _build_avail_rows(avail_results, visible_components)
    failed_avail = [comp for comp, status, _, _ in avail_rows if status == "error"]

    _CONFIG_NOTE = (
        "  Configuration files: .jejune/env-config · .jejune/env-secrets · .jejune/catalog.yaml"
    )
    all_hints = list(_CONFIG_HINTS.values()) or [""]
    all_avail_hints = list(_AVAIL_HINTS.values()) or [""]
    _W = max(
        len(_CONFIG_NOTE),
        2 + _W_SECT + 2 + _W_MSG + 2 + max(len(h) for h in all_hints + all_avail_hints),
        88,
    )

    role_label = f" [{_ACTIVE_ROLE}]" if _ACTIVE_ROLE else ""
    click.echo(f"jejune doctor{role_label}")

    # ── Configuration ────────────────────────────────────────────────
    click.echo(_section_sep("Configuration", _W))
    click.echo()
    note = _CONFIG_NOTE if _ACTIVE_ROLE in (None, "doc-steward") else None
    print_config_table(config_rows, note=note)
    click.echo()

    # ── Availability ─────────────────────────────────────────────────
    click.echo(_section_sep("Availability", _W))
    _print_avail_table(avail_rows, comp_header="Component availability", hint_header="Diagnostic hint")

    # ── Containers ───────────────────────────────────────────────────
    click.echo(_section_sep("Containers", _W))
    containers.print_containers_table()

    # ── Issues ───────────────────────────────────────────────────────
    if failed_config or failed_avail:
        click.echo()
        click.echo(_section_sep("Issues", _W))
        if failed_config:
            click.echo(click.style("Configuration issues:", fg="red"))
            click.echo()
            _WN = max(len(n) for n in failed_config)
            _WH = max(len(get_config_hint(n, "error", by_config[n][1])) for n in failed_config)
            for name in failed_config:
                detail = by_config[name][1]
                action = get_config_hint(name, "error", detail)
                click.echo(f"  {click.style(f'{name:<{_WN}}', fg='red')}  {action:<{_WH}}  [{detail}]")
        if failed_avail:
            if failed_config:
                click.echo()
            click.echo(click.style("Availability issues:", fg="red"))
            click.echo()
            _WN = max(len(n) for n in failed_avail)
            _WH = max(len(_AVAIL_HINTS.get(n, "investigate")) for n in failed_avail)
            for name in failed_avail:
                action = _AVAIL_HINTS.get(name, "investigate")
                detail = by_avail[name][1] if name in by_avail else "dependency failed"
                click.echo(f"  {click.style(f'{name:<{_WN}}', fg='red')}  {action:<{_WH}}  [{detail}]")


def _section_sep(title: str, width: int) -> str:
    prefix = f"====== {title} "
    return prefix + "=" * max(2, width - len(prefix))


def _build_avail_rows(
    avail_results: list[tuple[str, str, str]],
    all_visible: list[str],
) -> list[tuple[str, str, str, str]]:
    """Build (comp, status, check, hint) rows for the availability table."""
    by_avail = {comp: (status, msg) for comp, status, msg in avail_results}
    rows: list[tuple[str, str, str, str]] = []
    for comp in all_visible:
        if comp in by_avail:
            status, msg = by_avail[comp]
            if status == "ok":
                rows.append((comp, status, "", ""))
            else:
                hint = _AVAIL_HINTS.get(comp, "")
                if not hint:
                    deps = _COMPONENT_DEPS.get(comp, [])
                    for dep in sorted(deps, key=lambda d: _STATUS_RANK.get(by_avail.get(d, ("ok",))[0], 0), reverse=True):
                        if by_avail.get(dep, ("ok",))[0] != "ok":
                            hint = _AVAIL_HINTS.get(dep, "")
                            if hint:
                                break
                rows.append((comp, status, msg, hint))
        elif comp in _COMPONENT_DEPS:
            req = _COMPONENT_DEPS[comp]
            worst = max(
                (by_avail.get(dep, ("ok", ""))[0] for dep in req),
                key=lambda s: _STATUS_RANK.get(s, 0),
                default="ok",
            )
            failing = [dep for dep in req if by_avail.get(dep, ("ok", ""))[0] != "ok"]
            check = "" if worst == "ok" else "deps: " + ", ".join(failing)
            rows.append((comp, worst, check, ""))
    return rows


def _print_avail_table(
    rows: list[tuple[str, str, str, str]],
    comp_header: str = "Component",
    hint_header: str = "Hint",
) -> None:
    """Render Component | Status | Check | <hint_header> availability table."""
    if not rows:
        return
    _W_C = max(len(comp_header), max(len(r[0]) for r in rows))
    _W_S = max(len("Status"), max(len(r[1]) for r in rows))
    _W_K = max(len("Check"), max(len(r[2]) for r in rows))
    _W_H = max(len(hint_header), max(len(r[3]) for r in rows))
    click.echo(f"  {comp_header:<{_W_C}}  {'Status':<{_W_S}}  {'Check':<{_W_K}}  {hint_header}")
    click.echo("  " + "─" * (_W_C + 2 + _W_S + 2 + _W_K + 2 + _W_H))
    for comp, status, check, hint in rows:
        status_cell = click.style(f"{status:<{_W_S}}", fg=_STATUS_FG.get(status, "white"))
        click.echo(f"  {comp:<{_W_C}}  {status_cell}  {check:<{_W_K}}  {hint}")


def _avail_all_visible() -> list[str]:
    result = [c for c in _COMPONENTS if _is_visible(c)]
    for p in _REGISTRY:
        if _is_visible(p.name) and p.name not in result:
            result.append(p.name)
    return result


@click.command("check-availability")
def _config_check_availability():
    """Per-component availability diagnostic."""
    _, avail_results = run_all(components=_ACTIVE_COMPONENTS)
    rows = _build_avail_rows(avail_results, _avail_all_visible())
    if not rows:
        click.echo(click.style("No availability data for the current role.", fg="yellow"))
        return
    styled = [(click.style(comp, fg=_STATUS_FG.get(status, "white")), check) for comp, status, check, _ in rows]
    print_two_col_table(styled, "Component", "Check")


@click.command("status-availability")
def _config_status_availability():
    """Per-component availability status."""
    _, avail_results = run_all(components=_ACTIVE_COMPONENTS)
    rows = _build_avail_rows(avail_results, _avail_all_visible())
    if not rows:
        click.echo(click.style("No availability data for the current role.", fg="yellow"))
        return
    styled = [(comp, click.style(status, fg=_STATUS_FG.get(status, "white"))) for comp, status, _, _ in rows]
    print_two_col_table(styled, "Component", "Status")


@click.command("hint-availability")
def _config_hint_availability():
    """Availability hints for non-ok components."""
    _, avail_results = run_all(components=_ACTIVE_COMPONENTS)
    rows = [(comp, hint) for comp, _, _, hint in _build_avail_rows(avail_results, _avail_all_visible()) if hint]
    if not rows:
        click.echo(click.style("All components available.", fg="green"))
        return
    print_two_col_table(rows, "Component", "Hint")


@click.group(short_help="Availability checks for jejune components")
def availability():
    """Availability checks for jejune components."""


availability.add_command(_config_check_availability, "summary")


cli.add_command(configuration)
configuration.add_command(_config_check_availability)
configuration.add_command(_config_status_availability)
configuration.add_command(_config_hint_availability)
cli.add_command(containers_cli)
cli.add_command(neo4j)
cli.add_command(llm)
cli.add_command(llm_observability)
cli.add_command(graph)
cli.add_command(deployment)
cli.add_command(build)
cli.add_command(test_cmd)
cli.add_command(convert)
cli.add_command(availability)
cli.add_command(doctor)
cli.add_command(role)


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
    _W_SECT = max(len("Component configuration"), max(len(n) for n in _COMPONENTS))


_load_plugins()
