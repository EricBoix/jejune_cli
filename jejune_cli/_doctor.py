"""Doctor command and availability display helpers."""

import click

from .doctor_health_check import run_all, run_avail
from .click_comp_configuration import (
    print_two_col_table,
)
from .role_registry import ROLE_REGISTRY

# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------

_STATUS_FG: dict[str, str] = {"ok": "green", "warn": "yellow", "error": "red"}
_STATUS_ICON: dict[str, tuple[str, str]] = {
    "ok": ("✓", "green"),
    "warn": ("–", "yellow"),
    "error": ("✗", "red"),
}

from .component_base import base_comp
from .component_ext import ext_comp
from .component_registry import REGISTRY as COMP_REGISTRY
from .plugin_registry import PLUGIN_REGISTRY

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_avail_hint(inst: base_comp, fallback: str = "") -> str:
    deployment = COMP_REGISTRY.get("deployment")
    is_ui_dep = deployment is not None and any(
        dep.name == inst.name for dep in deployment.dependencies
    )
    if is_ui_dep and any(p.name == inst.name for p in PLUGIN_REGISTRY.plugins):
        images_missing = not deployment.is_available()
        return "run `jejune build`" if images_missing else "run `jejune up`"
    return inst.hint or fallback


def _build_avail_rows(
    avail_results: list[tuple[str, str, str]],
    all_visible: list[base_comp],
) -> list[tuple[str, str, str, str]]:
    """Build (comp, status, check, hint) rows for the availability table."""
    by_avail = {comp: (status, msg) for comp, status, msg in avail_results}
    rows: list[tuple[str, str, str, str]] = []
    for inst in all_visible:
        comp = inst.name
        if comp not in by_avail:
            continue
        status, msg = by_avail[comp]
        if status == "ok":
            rows.append((comp, status, "", ""))
        else:
            active_deps = inst.active_deps()
            failing_deps = [
                dep
                for dep in active_deps
                if by_avail.get(dep.name, ("ok",))[0] != "ok"
            ]
            hint = "" if failing_deps else _resolve_avail_hint(inst)
            rows.append((comp, status, msg, hint))
    return rows


def _print_health_table(
    config_rows: list[tuple[str, str, str, str]],
    avail_rows: list[tuple[str, str, str, str]],
    img_status: dict[str, bool],
) -> None:
    """Render merged Component | Config | Img | Avail | Action table."""
    if not config_rows:
        return
    by_avail = {r[0]: r for r in avail_rows}
    _COL_COMP = "Component"
    _COL_CFG = "Config"
    _COL_IMG = "Img"
    _COL_AVAIL = "Avail"
    _COL_ACT = "Action"
    _W_COMP = max(len(_COL_COMP), max(len(r[0]) for r in config_rows))
    _W_CFG = len(_COL_CFG)
    _W_IMG = len(_COL_IMG)
    _W_AVAIL = len(_COL_AVAIL)
    rows: list[tuple[str, str, bool | None, str | None, str]] = []
    for comp, c_status, _, c_hint in config_rows:
        avail = by_avail.get(comp)
        a_status = avail[1] if avail else None
        a_hint = avail[3] if avail else ""
        action = c_hint or (a_hint if a_status and a_status != "ok" else "")
        img = img_status.get(comp)
        rows.append((comp, c_status, img, a_status, action))
    _W_ACT = max(len(_COL_ACT), max(len(r[4]) for r in rows))
    divider_len = _W_COMP + 2 + _W_CFG + 2 + _W_IMG + 2 + _W_AVAIL + 2 + _W_ACT
    click.echo(
        f"  {_COL_COMP:<{_W_COMP}}  {_COL_CFG:<{_W_CFG}}"
        f"  {_COL_IMG:<{_W_IMG}}  {_COL_AVAIL:<{_W_AVAIL}}  {_COL_ACT}"
    )
    click.echo("  " + "─" * divider_len)
    for comp, c_status, img, a_status, action in rows:
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
        click.echo(f"  {comp:<{_W_COMP}}  {c_cell}  {i_cell}  {a_cell}  {action}")


# ---------------------------------------------------------------------------
# Doctor command
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Show all components, including those that are available.",
)
def doctor(verbose: bool):
    """Report component configuration and availability. Inspired by `brew doctor`.

    Two-stage check:\n
      Configuration — were the components configured by the user?\n
      Availability  — are the component services reachable?\n

    Followed by a Components summary showing which commands each enables.
    Only components relevant to the detected role are shown.
    Non configurable external components are hidden when available;
    use --verbose to show all.
    """
    from ._env import dot_jejune
    active_role_obj = ROLE_REGISTRY.detect_role()
    active_role = ROLE_REGISTRY.detect_role_name()

    d = dot_jejune()
    if (not active_role_obj or active_role_obj.is_doc_steward()) and not d.is_dir():
        click.echo(
            click.style(
                "Current working directory is not a jejune workspace.",
                fg="yellow",
            )
        )
        return

    config_results, avail_results, visible_components = run_all()

    by_config = {comp: (status, msg) for comp, status, msg in config_results}

    config_rows: list[tuple[str, str, str, str]] = []
    for comp in visible_components:
        status, msg = by_config.get(comp.name, ("ok", "ok"))
        hint = (
            (comp.configuration.hint or "")
            if status != "ok" and hasattr(comp, "configuration")
            else ""
        )
        config_rows.append((comp.name, status, msg if status != "ok" else "", hint))

    avail_rows = _build_avail_rows(avail_results, visible_components)

    _CONFIG_NOTE = "  Configuration files: .jejune/env-config · .jejune/env-secrets"

    role_label = f" [{active_role}]" if active_role else ""
    click.echo(click.style(f"jejune doctor{role_label}", bold=True))
    click.echo()

    if not verbose:
        avail_ok = {comp for comp, status, _, _ in avail_rows if status == "ok"}
        ext_names_set = {c.name for c in visible_components if isinstance(c, ext_comp)}
        config_rows = [
            row
            for row in config_rows
            if row[0] not in ext_names_set or row[0] not in avail_ok
        ]

    from .component_containerized import cont_comp
    img_status = cont_comp.image_build_status(visible_components)
    _print_health_table(config_rows, avail_rows, img_status)
    if active_role in (None, "doc-steward"):
        click.echo()
        click.echo(_CONFIG_NOTE)


# ---------------------------------------------------------------------------
# Availability subcommands (wired into `jejune configuration` by main.py)
# ---------------------------------------------------------------------------


@click.command("check-availability")
def config_check_availability():
    """Per-component availability diagnostic."""
    avail_results, visible = run_avail()
    rows = _build_avail_rows(avail_results, visible)
    if not rows:
        click.echo(
            click.style("No availability data for the current role.", fg="yellow")
        )
        return
    styled = [
        (click.style(comp, fg=_STATUS_FG.get(status, "white")), check)
        for comp, status, check, _ in rows
    ]
    print_two_col_table(styled, "Component", "Check")


@click.command("status-availability")
def config_status_availability():
    """Per-component availability status."""
    avail_results, visible = run_avail()
    rows = _build_avail_rows(avail_results, visible)
    if not rows:
        click.echo(
            click.style("No availability data for the current role.", fg="yellow")
        )
        return
    styled = [
        (comp, click.style(status, fg=_STATUS_FG.get(status, "white")))
        for comp, status, _, _ in rows
    ]
    print_two_col_table(styled, "Component", "Status")


@click.command("hint-availability")
def config_hint_availability():
    """Availability hints for non-ok components."""
    avail_results, visible = run_avail()
    rows = [
        (comp, hint)
        for comp, _, _, hint in _build_avail_rows(avail_results, visible)
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
