"""Doctor command and availability display helpers."""
from typing import Callable

import click

from ._health import run_all
from .component_ext import ext_comp
from .click_comp_configuration import (
    print_two_col_table,
)

# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------

_STATUS_RANK: dict[str, int] = {"error": 2, "warn": 1, "ok": 0}
_STATUS_FG: dict[str, str] = {"ok": "green", "warn": "yellow", "error": "red"}
_STATUS_ICON: dict[str, tuple[str, str]] = {
    "ok":    ("✓", "green"),
    "warn":  ("–", "yellow"),
    "error": ("✗", "red"),
}

_UI_PLUGIN_NAMES: frozenset[str] = frozenset(("docs-server", "kg-viewer", "md-browser"))

# Plugin-contributed optional dependencies (built-in optional deps live on component classes).
_PLUGIN_OPTIONAL_DEPS: dict[str, list[str]] = {}

# ---------------------------------------------------------------------------
# Component registry initialisation
# ---------------------------------------------------------------------------

from .component_base import base_comp
COMP_REGISTRY = base_comp.registry

base_comp.initialize_registry()


def _validate_registry() -> None:
    """Assert that all dependency instances in each component are registered."""
    for inst in COMP_REGISTRY:
        for dep in inst.dependencies + inst.optional_dependencies:
            assert COMP_REGISTRY.get(dep.name) is dep, (
                f"{inst.name}.dependencies contains unregistered instance {dep.name!r}"
            )


_validate_registry()

# ---------------------------------------------------------------------------
# Component availability
# ---------------------------------------------------------------------------


def component_available(name: str, _seen: set[str] | None = None) -> bool:
    """Return True if *name* and all its transitive required deps are available."""
    if _seen is None:
        _seen = set()
    if name in _seen:
        return True
    _seen.add(name)
    inst = COMP_REGISTRY.get(name)
    if inst is None:
        return True
    for dep in inst.dependencies:
        if not component_available(dep.name, _seen):
            return False
    return inst.is_available()


def requires_component(name: str) -> Callable[[], bool]:
    """Return a named condition predicate that checks *name* and its transitive deps."""
    def _check() -> bool:
        return component_available(name)
    _check.__name__ = f"{name.replace('-', '_')}_available"
    return _check


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _component_kind(name: str) -> str:
    """Return the Kind label for a component: "opt", "dep", or "" (blank)."""
    _optional_set = {
        dep.name
        for inst in COMP_REGISTRY
        for dep in inst.optional_dependencies
    } | {
        dep
        for deps in _PLUGIN_OPTIONAL_DEPS.values()
        for dep in deps
    }
    _required_set = {dep.name for inst in COMP_REGISTRY for dep in inst.dependencies}
    if name in _optional_set and name not in _required_set:
        return "opt"
    inst = COMP_REGISTRY.get(name)
    if inst is not None:
        return "dep" if isinstance(inst, ext_comp) else ""
    from .plugin import _REGISTRY as _PLUGIN_REGISTRY
    for p in _PLUGIN_REGISTRY:
        if p.name == name:
            return p.kind
    return ""


def _all_components() -> list[str]:
    """Return ordered component names from REGISTRY (built-ins + loaded plugins)."""
    return COMP_REGISTRY.names()


def _topo_sorted(components: list[str]) -> list[str]:
    """Return components in topological order using REGISTRY ordering."""
    comp_set = set(components)
    ordered = [name for name in COMP_REGISTRY.names() if name in comp_set]
    ordered += [name for name in components if name not in set(ordered)]
    return ordered


def _is_visible(name: str) -> bool:
    inst = COMP_REGISTRY.get(name)
    if inst is not None and inst.visible is not None and not inst.visible():
        return False
    from .role import detect_roles, role_components
    roles, _ = detect_roles()
    active = role_components(roles)
    return active is None or name in active


def _resolve_avail_hint(comp: str, fallback: str = "") -> str:
    from .plugin import _REGISTRY as _PLUGIN_REGISTRY
    if comp in _UI_PLUGIN_NAMES and any(p.name == comp for p in _PLUGIN_REGISTRY):
        from .ui_deployment import _deploy_images_missing
        try:
            return "run `jejune build`" if _deploy_images_missing() else "run `jejune up`"
        except Exception:
            return "run `jejune up`"
    inst = COMP_REGISTRY.get(comp)
    return (inst.hint or fallback) if inst else fallback


def _avail_all_visible() -> list[str]:
    return _topo_sorted([c for c in _all_components() if _is_visible(c)])


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
                inst = COMP_REGISTRY.get(comp)
                deps = inst.dependencies if inst else []
                failing_deps = [
                    dep for dep in deps
                    if by_avail.get(dep.name, ("ok",))[0] != "ok"
                ]
                hint = "" if failing_deps else _resolve_avail_hint(comp)
                rows.append((comp, status, msg, hint))
        else:
            inst = COMP_REGISTRY.get(comp)
            req = inst.dependencies if inst else []
            if req:
                worst = max(
                    (by_avail.get(dep.name, ("ok", ""))[0] for dep in req),
                    key=lambda s: _STATUS_RANK.get(s, 0),
                    default="ok",
                )
                failing = [dep.name for dep in req if by_avail.get(dep.name, ("ok", ""))[0] != "ok"]
                check = "" if worst == "ok" else "deps: " + ", ".join(failing)
                rows.append((comp, worst, check, ""))
    return rows


def _collect_img_status(visible: list[str]) -> dict[str, bool]:
    """Return {comp: image_built} for cont_comp components with is_built registered."""
    from .component_containerized import cont_comp
    result: dict[str, bool] = {}
    for comp in visible:
        inst = COMP_REGISTRY.get(comp)
        if isinstance(inst, cont_comp):
            try:
                result[comp] = inst.is_built()
            except Exception:
                pass
    return result


def _print_health_table(
    config_rows: list[tuple[str, str, str, str]],
    avail_rows: list[tuple[str, str, str, str]],
    img_status: dict[str, bool],
) -> None:
    """Render merged Component | Kind | Config | Img | Avail | Action table."""
    if not config_rows:
        return
    by_avail = {r[0]: r for r in avail_rows}
    _COL_COMP  = "Component"
    _COL_KIND  = "Kind"
    _COL_CFG   = "Config"
    _COL_IMG   = "Img"
    _COL_AVAIL = "Avail"
    _COL_ACT   = "Action"
    _W_COMP  = max(len(_COL_COMP), max(len(r[0]) for r in config_rows))
    _W_KIND  = len(_COL_KIND)
    _W_CFG   = len(_COL_CFG)
    _W_IMG   = len(_COL_IMG)
    _W_AVAIL = len(_COL_AVAIL)
    rows: list[tuple[str, str, str, bool | None, str | None, str]] = []
    for comp, c_status, _, c_hint in config_rows:
        avail = by_avail.get(comp)
        a_status = avail[1] if avail else None
        a_hint   = avail[3] if avail else ""
        action = c_hint or (a_hint if a_status and a_status != "ok" else "")
        img = img_status.get(comp)
        rows.append((comp, _component_kind(comp), c_status, img, a_status, action))
    _W_ACT = max(len(_COL_ACT), max(len(r[5]) for r in rows))
    divider_len = (
        _W_COMP + 2 + _W_KIND + 2 + _W_CFG + 2 + _W_IMG + 2 + _W_AVAIL + 2 + _W_ACT
    )
    click.echo(
        f"  {_COL_COMP:<{_W_COMP}}  {_COL_KIND:<{_W_KIND}}  {_COL_CFG:<{_W_CFG}}"
        f"  {_COL_IMG:<{_W_IMG}}  {_COL_AVAIL:<{_W_AVAIL}}  {_COL_ACT}"
    )
    click.echo("  " + "─" * divider_len)
    for comp, kind, c_status, img, a_status, action in rows:
        k_cell = f"{kind:<{_W_KIND}}"
        c_icon, c_fg = _STATUS_ICON.get(c_status, ("?", "white"))
        c_cell = click.style(c_icon, fg=c_fg) + " " * (_W_CFG - len(c_icon))
        if img is None:
            i_cell = " " * _W_IMG
        else:
            i_icon, i_fg = ("✓", "green") if img else ("✗", "red")
            i_cell = click.style(i_icon, fg=i_fg) + " " * (_W_IMG - len(i_icon))
        if a_status is not None:
            a_icon, a_fg = _STATUS_ICON.get(a_status, ("?", "white"))
            a_cell = click.style(a_icon, fg=a_fg) + " " * (_W_AVAIL - len(a_icon))
        else:
            a_cell = " " * _W_AVAIL
        click.echo(f"  {comp:<{_W_COMP}}  {k_cell}  {c_cell}  {i_cell}  {a_cell}  {action}")


# ---------------------------------------------------------------------------
# Doctor command
# ---------------------------------------------------------------------------

@click.command()
@click.option("--verbose", is_flag=True, default=False, help="Show all components, including those that are available.")
def doctor(verbose: bool):
    """Report component configuration and availability. Inspired by `brew doctor`.

    Two-stage check:\n
      Configuration — were the components configured by the user?\n
      Availability  — are the component services reachable?\n

    Followed by a Components summary showing which commands each enables.
    Only components relevant to the detected role are shown.
    External infrastructure components (network, git-command, git-server,
    docker, extensions) are hidden when available; use --verbose to show all.
    """
    from ._env import dot_jejune
    from .plugin import _REGISTRY as _PLUGIN_REGISTRY
    from .role import detect_role, detect_roles, role_components

    active_role, _ = detect_role()
    active_roles, _ = detect_roles()
    active_components = role_components(active_roles)

    d = dot_jejune()
    if active_role in (None, "doc-steward") and not d.is_dir():
        click.echo(
            click.style(
                "Current working directory is not a jejune workspace.",
                fg="yellow",
            )
        )
        return

    config_results, avail_results = run_all(components=active_components)

    _plugin_names = {p.name for p in _PLUGIN_REGISTRY}
    _builtin = frozenset(COMP_REGISTRY.names())
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

    all_comp = _all_components()
    visible_components = [c for c in all_comp if _is_visible(c)]
    for name in (sorted(active_components - _builtin) if active_components else []):
        if name not in visible_components:
            visible_components.append(name)
    visible_components = _topo_sorted(visible_components)

    visible_set = set(visible_components)
    config_rows: list[tuple[str, str, str, str]] = []
    for comp in COMP_REGISTRY:
        if comp.name not in visible_set:
            continue
        status, msg = by_config.get(comp.name, ("ok", "ok"))
        hint = (comp.configuration.hint or "") if status != "ok" and hasattr(comp, 'configuration') else ""
        config_rows.append((comp.name, status, msg if status != "ok" else "", hint))

    avail_rows = _build_avail_rows(avail_results, visible_components)

    _CONFIG_NOTE = "  Configuration files: .jejune/env-config · .jejune/env-secrets"

    role_label = f" [{active_role}]" if active_role else ""
    click.echo(click.style(f"jejune doctor{role_label}", bold=True))
    click.echo()

    if not verbose:
        avail_ok = {comp for comp, status, _, _ in avail_rows if status == "ok"}
        config_rows = [
            row for row in config_rows
            if not (isinstance(COMP_REGISTRY.get(row[0]), ext_comp) and row[0] in avail_ok)
        ]

    img_status = _collect_img_status(visible_components)
    _print_health_table(config_rows, avail_rows, img_status)
    if active_role in (None, "doc-steward"):
        click.echo()
        click.echo(_CONFIG_NOTE)


# ---------------------------------------------------------------------------
# Availability subcommands (wired into `jejune configuration` by main.py)
# ---------------------------------------------------------------------------

def _active_components():
    from .role import detect_roles, role_components
    roles, _ = detect_roles()
    return role_components(roles)


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
