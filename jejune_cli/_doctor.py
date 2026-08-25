"""Doctor command and availability display helpers."""
import click

from . import containers
from ._health import run_all
from .configuration import (
    COMPONENT_CONFIG_HINTS as _CONFIG_HINTS,
    get_config_hint,
    print_config_table,
    print_two_col_table,
)

# ---------------------------------------------------------------------------
# Component registry — _BASE_COMPONENTS is the ordered list of built-in
# component names.  main.py imports it to seed _COMPONENTS and _BUILTIN_COMPONENTS.
# ---------------------------------------------------------------------------

_BASE_COMPONENTS: list[str] = [
    "ecosystem",
    "neo4j",
    "llm",
    "llm-observability",
    "graph",
    "deployment",
    "convert",
]

# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------

_STATUS_RANK: dict[str, int] = {"error": 2, "warn": 1, "ok": 0}
_STATUS_FG: dict[str, str] = {"ok": "green", "warn": "yellow", "error": "red"}

# ---------------------------------------------------------------------------
# Availability metadata — populated by main._load_plugins() at startup.
# ---------------------------------------------------------------------------

_AVAIL_HINTS: dict[str, str] = {
    "neo4j":              "run `jejune neo4j start --help`",
    "llm":                "run `jejune llm status`",
    "llm-observability":  "run `jejune llm-observability start`",
    "convert":            "run `jejune convert build`",
    "docs-server":        "run `jejune deployment extensions install`",
    "kg-viewer":          "run `jejune deployment extensions install`",
    "md-browser":         "run `jejune deployment extensions install`",
}

_UI_PLUGIN_NAMES: frozenset[str] = frozenset(("docs-server", "kg-viewer", "md-browser"))

# Required dependencies: a component is only effective when all its deps are ok.
_COMPONENT_DEPS: dict[str, list[str]] = {
    "graph":      ["neo4j", "llm"],
    "deployment": ["catalog"],
}

# Optional dependencies: enhance a component but do not affect its effective status.
_COMPONENT_OPTIONAL_DEPS: dict[str, list[str]] = {
    "graph": ["llm-observability"],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_components() -> list[str]:
    """Return ordered component names: built-ins first, then loaded plugins."""
    from .plugin import _REGISTRY
    seen = set(_BASE_COMPONENTS)
    result = list(_BASE_COMPONENTS)
    for p in _REGISTRY:
        if p.name not in seen:
            result.append(p.name)
            seen.add(p.name)
    return result


def _is_visible(name: str) -> bool:
    from .role import detect_roles, role_components
    active = role_components(detect_roles())
    return active is None or name in active


def _resolve_avail_hint(comp: str, fallback: str = "") -> str:
    from .plugin import _REGISTRY
    if comp in _UI_PLUGIN_NAMES and any(p.name == comp for p in _REGISTRY):
        from .ui_deployment import _deploy_images_missing
        try:
            return "run `jejune build`" if _deploy_images_missing() else "run `jejune up`"
        except Exception:
            return "run `jejune up`"
    return _AVAIL_HINTS.get(comp, fallback)


def _section_sep(title: str, width: int) -> str:
    prefix = f"====== {title} "
    return prefix + "=" * max(2, width - len(prefix))


def _avail_all_visible() -> list[str]:
    return [c for c in _all_components() if _is_visible(c)]


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
                hint = _resolve_avail_hint(comp)
                if not hint:
                    deps = _COMPONENT_DEPS.get(comp, [])
                    for dep in sorted(
                        deps,
                        key=lambda d: _STATUS_RANK.get(by_avail.get(d, ("ok",))[0], 0),
                        reverse=True,
                    ):
                        if by_avail.get(dep, ("ok",))[0] != "ok":
                            hint = _resolve_avail_hint(dep)
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


# ---------------------------------------------------------------------------
# Doctor command
# ---------------------------------------------------------------------------

@click.command()
def doctor():
    """Report component configuration and availability. Inspired by `brew doctor`.

    Two-stage check:\n
      Configuration — were the components configured by the user?\n
      Availability  — are the component services reachable?\n

    Followed by a Components summary showing which commands each enables.
    Only components relevant to the detected role are shown.
    """
    from ._env import dot_jejune
    from .plugin import _REGISTRY
    from .role import detect_role, detect_roles, role_components

    active_role, _ = detect_role()
    active_components = role_components(detect_roles())

    d = dot_jejune()
    if active_role in (None, "doc-steward") and not d.is_dir():
        click.echo(
            click.style(
                f"No .jejune/ directory found in {d.parent}.\n"
                "Run `jejune configuration doc-steward init` to set up the workspace.",
                fg="yellow",
            )
        )
        raise SystemExit(1)

    config_results, avail_results = run_all(components=active_components)

    # Show placeholder rows for expected components not covered by built-ins or
    # registered plugins (e.g. deployer check extensions not yet installed).
    _plugin_names = {p.name for p in _REGISTRY}
    _builtin = frozenset(_BASE_COMPONENTS)
    if active_components is not None:
        _seen_config = {c for c, _, _ in config_results}
        _seen_avail  = {c for c, _, _ in avail_results}
        for name in sorted(active_components - _builtin):
            if name not in _plugin_names:
                if name not in _seen_config:
                    config_results.append((name, "warn", "extension not installed"))
                if name not in _seen_avail:
                    avail_results.append((name, "warn", "extension not installed"))

    by_config = {comp: (status, msg) for comp, status, msg in config_results}
    by_avail = {comp: (status, msg) for comp, status, msg in avail_results}

    all_comp = _all_components()
    visible_components = [c for c in all_comp if _is_visible(c)]
    for name in (sorted(active_components - _builtin) if active_components else []):
        if name not in visible_components:
            visible_components.append(name)

    _W_SECT = max(len("Component configuration"), max((len(n) for n in all_comp), default=0))
    _W_MSG = 16

    config_rows: list[tuple[str, str, str, str]] = [
        (
            comp,
            status,
            msg if status != "ok" else "",
            "" if status == "ok" else get_config_hint(comp, status, msg),
        )
        for comp, (status, msg) in [
            (c, by_config.get(c, ("ok", "ok"))) for c in visible_components
        ]
    ]
    failed_config = [comp for comp, status, _, _ in config_rows if status == "error"]

    avail_rows = _build_avail_rows(avail_results, visible_components)
    failed_avail = [comp for comp, status, _, _ in avail_rows if status == "error"]

    _CONFIG_NOTE = "  Configuration files: .jejune/env-config · .jejune/env-secrets"
    all_hints = list(_CONFIG_HINTS.values()) or [""]
    all_avail_hints = list(_AVAIL_HINTS.values()) or [""]
    _W = max(
        len(_CONFIG_NOTE),
        2 + _W_SECT + 2 + _W_MSG + 2 + max(len(h) for h in all_hints + all_avail_hints),
        88,
    )

    role_label = f" [{active_role}]" if active_role else ""
    click.echo(f"jejune doctor{role_label}")

    click.echo(_section_sep("Configuration", _W))
    click.echo()
    note = _CONFIG_NOTE if active_role in (None, "doc-steward") else None
    print_config_table(config_rows, note=note)
    click.echo()

    click.echo(_section_sep("Availability", _W))
    _print_avail_table(avail_rows, comp_header="Component availability", hint_header="Diagnostic hint")

    click.echo(_section_sep("Containers", _W))
    containers.print_containers_table()

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
            _WH = max(len(_resolve_avail_hint(n, "investigate")) for n in failed_avail)
            for name in failed_avail:
                action = _resolve_avail_hint(name, "investigate")
                detail = by_avail[name][1] if name in by_avail else "dependency failed"
                click.echo(f"  {click.style(f'{name:<{_WN}}', fg='red')}  {action:<{_WH}}  [{detail}]")


# ---------------------------------------------------------------------------
# Availability subcommands (wired into `jejune configuration` by main.py)
# ---------------------------------------------------------------------------

def _active_components():
    from .role import detect_roles, role_components
    return role_components(detect_roles())


@click.command("check-availability")
def config_check_availability():
    """Per-component availability diagnostic."""
    _, avail_results = run_all(components=_active_components())
    rows = _build_avail_rows(avail_results, _avail_all_visible())
    if not rows:
        click.echo(click.style("No availability data for the current role.", fg="yellow"))
        return
    styled = [
        (click.style(comp, fg=_STATUS_FG.get(status, "white")), check)
        for comp, status, check, _ in rows
    ]
    print_two_col_table(styled, "Component", "Check")


@click.command("status-availability")
def config_status_availability():
    """Per-component availability status."""
    _, avail_results = run_all(components=_active_components())
    rows = _build_avail_rows(avail_results, _avail_all_visible())
    if not rows:
        click.echo(click.style("No availability data for the current role.", fg="yellow"))
        return
    styled = [
        (comp, click.style(status, fg=_STATUS_FG.get(status, "white")))
        for comp, status, _, _ in rows
    ]
    print_two_col_table(styled, "Component", "Status")


@click.command("hint-availability")
def config_hint_availability():
    """Availability hints for non-ok components."""
    _, avail_results = run_all(components=_active_components())
    rows = [
        (comp, hint)
        for comp, _, _, hint in _build_avail_rows(avail_results, _avail_all_visible())
        if hint
    ]
    if not rows:
        click.echo(click.style("All components available.", fg="green"))
        return
    print_two_col_table(rows, "Component", "Hint")


@click.group(short_help="Availability checks for jejune components")
def availability():
    """Availability checks for jejune components."""


availability.add_command(config_check_availability, "summary")
