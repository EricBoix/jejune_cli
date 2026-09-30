"""Doctor command and availability display helpers."""

from pathlib import Path

import click

from .app_context import AppContext
from .doctor_health_check import run_all, run_avail
from .click_helpers import print_two_col_table
from .click_theme import ClickTheme
from .component_base import base_comp
from .component_containerized import cont_comp
from .component_ext import ext_comp
from .component_ext_server import ext_server
from .component_with_config import conf_comp
from .plugin_registry import PluginRegistry
from .role_registry import RoleRegistry
from .dot_jejune import dot_jejune
from .doctor_column import Column

# ---------------------------------------------------------------------------
# Shared availability helper
# ---------------------------------------------------------------------------


def _resolve_avail_hint(
    inst: base_comp,
    role_registry: RoleRegistry,
    plugin_registry: PluginRegistry,
    fallback: str = "",
) -> str:
    if inst.name == "catalog":
        return "run `jejune catalog check`"
    deployer = role_registry.get("deployer")
    is_deployer_plugin = (
        deployer is not None
        and inst.name in deployer.component_names
        and any(p.name == inst.name for p in plugin_registry.plugins)
    )
    if is_deployer_plugin:
        if isinstance(inst, cont_comp) and not inst.is_built():
            return "run `jejune build`"
        return "run `jejune up`"
    return inst.hint or fallback


def _failing_dep_names_per_component(
    avail_results: list[tuple[str, str, str]],
    active_components: list[base_comp],
) -> dict[str, list[str]]:
    by_status = {comp: status for comp, status, _ in avail_results}
    return {
        inst.name: [dep.name for dep in inst.active_deps()
                    if by_status.get(dep.name, "ok") != "ok"]
        for inst in active_components
        if inst.name in by_status
    }

# ---------------------------------------------------------------------------
# Doctor table column factories
# ---------------------------------------------------------------------------


def _config_column(
    config_results: list[tuple[str, str, str]],
    active_components: list[base_comp],
    port_conflict_hints: dict[str, str],
) -> Column:
    by_config = {comp: (status, msg) for comp, status, msg in config_results}
    cells: dict[str, tuple[str, str]] = {}
    for inst in active_components:
        comp = inst.name
        if not isinstance(inst, conf_comp):
            cells[comp] = ("", "")
            continue
        status, _ = by_config.get(comp, ("ok", ""))
        icon, fg = ClickTheme.status_icons.get(status, ("?", "white"))
        if status != "ok" and hasattr(inst, "configuration"):
            hint = ", ".join(inst.configuration.effective_hints(port_conflict_hints)) or ""
        else:
            hint = ""
        styled = click.style(icon, fg=fg)
        cells[comp] = (icon, styled)
    return Column("Config", cells)


def _img_column(
    active_components: list[base_comp],
    img_status: dict[str, bool],
    external_image_names: set[str],
) -> Column:
    cells: dict[str, tuple[str, str]] = {}
    for inst in active_components:
        comp = inst.name
        built = img_status.get(comp)
        if built is None:
            cells[comp] = ("", "")
        elif built:
            icon = "✓"
            cells[comp] = (icon, click.style(icon, fg="green"))
        elif comp in external_image_names:
            icon = "–"
            cells[comp] = (icon, click.style(icon, fg="yellow"))
        else:
            icon = "✗"
            cells[comp] = (icon, click.style(icon, fg="red"))
    return Column("Img", cells)


def _avail_column(
    avail_results: list[tuple[str, str, str]],
    failing_deps: dict[str, list[str]],
) -> Column:
    by_avail = {comp: status for comp, status, _ in avail_results}
    cells: dict[str, tuple[str, str]] = {}
    for comp, status in by_avail.items():
        effective_status = "error" if failing_deps.get(comp) else status
        icon, fg = ClickTheme.status_icons.get(effective_status, ("?", "white"))
        cells[comp] = (icon, click.style(icon, fg=fg))
    return Column("Avail", cells)


def _action_column(
    config_results: list[tuple[str, str, str]],
    avail_results: list[tuple[str, str, str]],
    active_components: list[base_comp],
    failing_deps: dict[str, list[str]],
    port_conflict_per_comp: dict[str, str],
    role_registry: RoleRegistry,
    plugin_registry: PluginRegistry,
) -> Column:
    by_config = {comp: (status, msg) for comp, status, msg in config_results}
    by_avail = {comp: (status, msg) for comp, status, msg in avail_results}
    inst_by_name = {inst.name: inst for inst in active_components}
    cells: dict[str, tuple[str, str]] = {}
    for comp in inst_by_name:
        inst = inst_by_name[comp]
        c_status, _ = by_config.get(comp, ("ok", ""))
        a_status, a_msg = by_avail.get(comp, ("ok", ""))
        has_failing_deps = bool(failing_deps.get(comp))
        if has_failing_deps:
            a_hint = "Fix " + ", ".join(failing_deps[comp]) + " availability"
        else:
            a_hint = _resolve_avail_hint(inst, role_registry, plugin_registry) if a_status != "ok" else ""
        if c_status != "ok" and hasattr(inst, "configuration"):
            c_hint = ", ".join(inst.configuration.effective_hints(port_conflict_per_comp)) or ""
        else:
            c_hint = ""
        action = (
            port_conflict_per_comp.get(comp)
            or (a_hint if has_failing_deps else "")
            or c_hint
            or (a_hint if a_status != "ok" else "")
        )
        cells[comp] = (action, action)
    return Column("Action", cells)

# ---------------------------------------------------------------------------
# Availability subcommand column factories
# ---------------------------------------------------------------------------


def _avail_check_column(
    avail_results: list[tuple[str, str, str]],
    active_components: list[base_comp],
    failing_deps: dict[str, list[str]],
) -> Column:
    """check-availability: items() → (styled_comp, check_text)."""
    by_avail = {comp: (status, msg) for comp, status, msg in avail_results}
    inst_by_name = {inst.name: inst for inst in active_components}
    cells: dict[str, tuple[str, str]] = {}
    styled_keys: dict[str, str] = {}
    for comp in inst_by_name:
        if comp not in by_avail:
            continue
        status, msg = by_avail[comp]
        if failing_deps.get(comp):
            effective_status = "error"
            check_text = "dependency unavailable"
        else:
            effective_status = status
            check_text = "" if status == "ok" else msg
        fg = ClickTheme.status_foregrounds.get(effective_status, "white")
        styled_keys[comp] = click.style(comp, fg=fg)
        cells[comp] = (check_text, check_text)
    return Column("Check", cells, styled_keys)


def _avail_status_column(
    avail_results: list[tuple[str, str, str]],
    active_components: list[base_comp],
    failing_deps: dict[str, list[str]],
) -> Column:
    """status-availability: items() → (comp, styled_status)."""
    by_avail = {comp: (status, msg) for comp, status, msg in avail_results}
    inst_by_name = {inst.name: inst for inst in active_components}
    cells: dict[str, tuple[str, str]] = {}
    for comp in inst_by_name:
        if comp not in by_avail:
            continue
        status, _ = by_avail[comp]
        effective_status = "error" if failing_deps.get(comp) else status
        fg = ClickTheme.status_foregrounds.get(effective_status, "white")
        cells[comp] = (effective_status, click.style(effective_status, fg=fg))
    return Column("Status", cells)


def _avail_hint_column(
    avail_results: list[tuple[str, str, str]],
    active_components: list[base_comp],
    failing_deps: dict[str, list[str]],
    role_registry: RoleRegistry,
    plugin_registry: PluginRegistry,
) -> Column:
    """hint-availability: non_empty_items() → (comp, hint)."""
    by_avail = {comp: (status, msg) for comp, status, msg in avail_results}
    inst_by_name = {inst.name: inst for inst in active_components}
    cells: dict[str, tuple[str, str]] = {}
    for comp, inst in inst_by_name.items():
        if comp not in by_avail:
            continue
        status, _ = by_avail[comp]
        if failing_deps.get(comp):
            hint = "Fix " + ", ".join(failing_deps[comp]) + " availability"
        elif status != "ok":
            hint = _resolve_avail_hint(inst, role_registry, plugin_registry)
        else:
            hint = ""
        cells[comp] = (hint, hint)
    return Column("Hint", cells)

# ---------------------------------------------------------------------------
# Doctor table renderer
# ---------------------------------------------------------------------------


def _print_health_table(
    component_names: list[str],
    columns: list[Column],
) -> None:
    if not component_names:
        return
    w_comp = max(len("Component"), max(len(name) for name in component_names))
    headers = "  ".join(col.render_header() for col in columns)
    divider_len = w_comp + sum(2 + col.width for col in columns)
    click.echo(f"  {'Component':<{w_comp}}  {headers}")
    click.echo("  " + "─" * divider_len)
    for name in component_names:
        cells = "  ".join(col.render_cell(name) for col in columns)
        click.echo(f"  {name:<{w_comp}}  {cells}")

# ---------------------------------------------------------------------------
# Doctor command helpers (extracted from doctor())
# ---------------------------------------------------------------------------


def _resolve_port_conflict_hints(active_components: list[base_comp]) -> dict[str, str]:
    deploy_comp = next(
        (c for c in active_components if c.name == "deployment"), None
    )
    if deploy_comp is not None and hasattr(deploy_comp, "hint_for_occupied_ports"):
        return deploy_comp.hint_for_occupied_ports(Path("."))
    return {}


def _compute_port_conflict_per_comp(
    active_components: list[base_comp],
    failing_deps: dict[str, list[str]],
    port_conflict_hints: dict[str, str],
) -> dict[str, str]:
    if not port_conflict_hints:
        return {}
    port_conflict_per_comp: dict[str, str] = {}
    for inst in active_components:
        if not hasattr(inst, "configuration"):
            continue
        if failing_deps.get(inst.name):
            continue
        comp_conflicts = [
            port_conflict_hints[entry.env_var]
            for entry in inst.configuration
            if entry.env_var in port_conflict_hints
        ]
        if comp_conflicts:
            port_conflict_per_comp[inst.name] = ", ".join(comp_conflicts)
    return port_conflict_per_comp


def _visible_component_names(
    config_results: list[tuple[str, str, str]],
    avail_results: list[tuple[str, str, str]],
    active_components: list[base_comp],
    verbose: bool,
) -> list[str]:
    has_data = {comp for comp, _, _ in config_results} | {comp for comp, _, _ in avail_results}
    all_names = [c.name for c in active_components if c.name in has_data]
    if verbose:
        return all_names
    avail_ok = {comp for comp, status, _ in avail_results if status == "ok"}
    ext_names = {c.name for c in active_components if isinstance(c, (ext_comp, ext_server))}
    return [name for name in all_names if name not in ext_names or name not in avail_ok]

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
@click.pass_context
def doctor(ctx, verbose: bool):
    """Report component configuration and availability. Inspired by `brew doctor`.

    Two-stage check:\n
      Configuration — were the components configured by the user?\n
      Availability  — are the component services reachable?\n

    Followed by a Components summary showing which commands each enables.
    Only components relevant to the detected role are shown.
    Non configurable external components are hidden when available;
    use --verbose to show all.
    """
    app = ctx.find_object(AppContext)
    active_role_obj = app.role_registry.detect_role()
    active_role = app.role_registry.detect_role_name()

    d = dot_jejune()
    if (not active_role_obj or app.role_registry.role_inherits(active_role_obj, "doc-steward")) and not d.is_dir():
        click.echo(
            click.style(
                "Current working directory is not a jejune workspace.",
                fg="yellow",
            )
        )
        return

    config_results, avail_results, active_components = run_all(
        app.component_registry, app.role_registry, app.plugin_registry
    )
    port_conflict_hints    = _resolve_port_conflict_hints(active_components)
    failing_deps           = _failing_dep_names_per_component(avail_results, active_components)
    port_conflict_per_comp = _compute_port_conflict_per_comp(
        active_components, failing_deps, port_conflict_hints)
    img_status           = cont_comp.image_build_status(active_components)
    external_image_names = {
        c.name for c in active_components
        if isinstance(c, cont_comp) and c.is_external_image
    }
    component_names = _visible_component_names(
        config_results, avail_results, active_components, verbose)

    _CONFIG_NOTE = "  Configuration files: .jejune/env-config · .jejune/env-secrets"
    role_label = f" [{active_role}]" if active_role else ""
    click.echo(click.style(f"jejune doctor{role_label}", bold=True))
    click.echo()

    config_column = _config_column(config_results, active_components, port_conflict_hints)
    img_column    = _img_column(active_components, img_status, external_image_names)
    avail_column  = _avail_column(avail_results, failing_deps)
    action_column = _action_column(
        config_results, avail_results, active_components,
        failing_deps, port_conflict_per_comp,
        app.role_registry, app.plugin_registry,
    )
    columns: list[Column] = [
        config_column,
        img_column,
        avail_column,
        action_column,
    ]
    _print_health_table(component_names, columns)
    if active_role is None or app.role_registry.role_inherits(active_role, "doc-steward"):
        click.echo()
        click.echo(_CONFIG_NOTE)


# ---------------------------------------------------------------------------
# Availability subcommands (wired into `jejune configuration` by main.py)
# ---------------------------------------------------------------------------


@click.command("check-availability")
@click.pass_context
def config_check_availability(ctx):
    """Per-component availability diagnostic."""
    app = ctx.find_object(AppContext)
    avail_results, active_components = run_avail(
        app.component_registry, app.role_registry, app.plugin_registry
    )
    failing_deps = _failing_dep_names_per_component(avail_results, active_components)
    col = _avail_check_column(avail_results, active_components, failing_deps)
    if not col.items():
        click.echo(
            click.style("No availability data for the current role.", fg="yellow")
        )
        return
    print_two_col_table(col.items(), "Component", "Check")


@click.command("status-availability")
@click.pass_context
def config_status_availability(ctx):
    """Per-component availability status."""
    app = ctx.find_object(AppContext)
    avail_results, active_components = run_avail(
        app.component_registry, app.role_registry, app.plugin_registry
    )
    failing_deps = _failing_dep_names_per_component(avail_results, active_components)
    col = _avail_status_column(avail_results, active_components, failing_deps)
    if not col.items():
        click.echo(
            click.style("No availability data for the current role.", fg="yellow")
        )
        return
    print_two_col_table(col.items(), "Component", "Status")


@click.command("hint-availability")
@click.pass_context
def config_hint_availability(ctx):
    """Availability hints for non-ok components."""
    app = ctx.find_object(AppContext)
    avail_results, active_components = run_avail(
        app.component_registry, app.role_registry, app.plugin_registry
    )
    failing_deps = _failing_dep_names_per_component(avail_results, active_components)
    col = _avail_hint_column(avail_results, active_components, failing_deps, app.role_registry, app.plugin_registry)
    rows = col.non_empty_items()
    if not rows:
        click.echo(click.style("All components available.", fg="green"))
        return
    print_two_col_table(rows, "Component", "Hint")


@click.group(short_help="Availability checks for jejune components")
def availability():
    """Availability checks for jejune components."""


availability.add_command(config_check_availability, "summary")
