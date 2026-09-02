"""Doctor command and availability display helpers."""
from typing import Callable

import click

from ._health import run_all
from .configuration import (
    get_config_hint,
    print_two_col_table,
)

# ---------------------------------------------------------------------------
# Component registry — _BASE_COMPONENTS is the ordered list of built-in
# component names.  main.py imports it to seed _COMPONENTS and _BUILTIN_COMPONENTS.
# ---------------------------------------------------------------------------

_BASE_COMPONENTS: list[str] = [
    "ecosystem",
    "network",
    "git-command",
    "git-repos-access",
    "docker-command",
    "docker-hub-server",
    "pypi-server",
    "uv-command",
    "extensions",
    "catalog",
    "neo4j",
    "llm",
    "llm-observability",
    "graph",
    "deployment",
    "docs-server",
    "kg-viewer",
    "md-browser",
    "convert",
    "manifest",
]

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

# ---------------------------------------------------------------------------
# Availability metadata — populated by main._load_plugins() at startup.
# ---------------------------------------------------------------------------

_AVAIL_HINTS: dict[str, str] = {
    "network":            "check internet connectivity (GitHub must be reachable)",
    "git-command":        "install git (https://git-scm.com)",
    "docker-command":     "install Docker Desktop (https://docs.docker.com/get-docker/)",
    "neo4j":              "run `jejune neo4j start --help`",
    "llm":                "run `jejune llm status-config`",
    "llm-observability":  "run `jejune llm-observability start`",
    "convert":            "run `jejune convert build`",
    "uv-command":         "install uv (https://docs.astral.sh/uv/getting-started/installation/)",
    "extensions":         "run `jejune deployment install`",
    "docs-server":        "run `jejune deployment install`",
    "kg-viewer":          "run `jejune deployment install`",
    "md-browser":         "run `jejune deployment install`",
}

_UI_PLUGIN_NAMES: frozenset[str] = frozenset(("docs-server", "kg-viewer", "md-browser"))

# Required dependencies: a component is only effective when all its deps are ok.
_COMPONENT_DEPS: dict[str, list[str]] = {
    "git-repos-access": ["network", "git-command"],
    "docker-hub-server": ["network"],
    "pypi-server":  ["network"],
    "ecosystem":    ["git-repos-access"],
    "extensions":   ["git-repos-access", "uv-command"],
    "neo4j":        ["git-repos-access", "docker-hub-server"],
    "llm":          ["network"],
    "graph":        ["git-repos-access", "neo4j", "llm"],
    "catalog":      ["ecosystem"],
    "deployment":   ["catalog"],
    "convert":      ["pypi-server"],
    "docs-server":  ["ecosystem", "docker-command"],
    "kg-viewer":    ["ecosystem", "docker-command"],
    "md-browser":   ["ecosystem", "docker-command"],
}

# Optional dependencies: enhance a component but do not affect its effective status.
_COMPONENT_OPTIONAL_DEPS: dict[str, list[str]] = {
    "graph": ["llm-observability"],
}

# External dependencies: components the user must install/provide (not jejune-managed).
# Values are (kind, fix_step_label). fix_step_label is the HeuristicStep label for restoring
# this dep's availability, or None for deps without a dedicated fix step.
_COMPONENT_KIND: dict[str, tuple[str, str | None]] = {
    "network":           ("dep", "Check network connectivity"),
    "git-command":       ("dep", "Install git"),
    "git-repos-access":  ("dep", None),
    "ecosystem":         ("dep", None),
    "docker-command":    ("dep", "Install docker desktop"),
    "docker-hub-server": ("dep", None),
    "pypi-server":       ("dep", None),
    "uv-command":        ("dep", "Install uv"),
    "extensions":        ("dep", "Install deployment"),
    "llm":               ("dep", None),
}

# Visibility predicates: when the predicate returns False the component is hidden.
_COMPONENT_VISIBLE: dict[str, Callable[[], bool]] = {}

# Components hidden from the default doctor output when they are available.
_HIDE_WHEN_AVAILABLE: frozenset[str] = frozenset(
    ("network", "git-command", "git-repos-access", "docker-command", "uv-command", "extensions")
)


def _init_visibility() -> None:
    from .ecosystem import ecosystem_needs_remote
    _COMPONENT_VISIBLE["network"]          = ecosystem_needs_remote
    _COMPONENT_VISIBLE["git-command"]      = ecosystem_needs_remote
    _COMPONENT_VISIBLE["git-repos-access"] = ecosystem_needs_remote


_init_visibility()


def _validate_component_names() -> None:
    """Assert that all component-name keys in built-in dicts are in _BASE_COMPONENTS."""
    _base = frozenset(_BASE_COMPONENTS)
    _flat_deps = {d for deps in _COMPONENT_DEPS.values() for d in deps}
    _flat_opt  = {d for deps in _COMPONENT_OPTIONAL_DEPS.values() for d in deps}
    for lbl, names in [
        ("_AVAIL_HINTS keys",               _AVAIL_HINTS),
        ("_COMPONENT_DEPS keys",            _COMPONENT_DEPS),
        ("_COMPONENT_DEPS values",          _flat_deps),
        ("_COMPONENT_KIND keys",            _COMPONENT_KIND),
        ("_COMPONENT_OPTIONAL_DEPS keys",   _COMPONENT_OPTIONAL_DEPS),
        ("_COMPONENT_OPTIONAL_DEPS values", _flat_opt),
        ("_HIDE_WHEN_AVAILABLE",            _HIDE_WHEN_AVAILABLE),
    ]:
        unknown = set(names) - _base
        assert not unknown, f"{lbl} contain unknown component names: {unknown}"


_validate_component_names()

# ---------------------------------------------------------------------------
# Component availability registry
# ---------------------------------------------------------------------------

_COMPONENT_AVAIL: dict[str, Callable[[], bool]] = {}
_COMPONENT_AVAIL_INITIALIZED = False


def _init_component_avail() -> None:
    global _COMPONENT_AVAIL_INITIALIZED
    if _COMPONENT_AVAIL_INITIALIZED:
        return
    _COMPONENT_AVAIL_INITIALIZED = True
    from .network         import is_network_available
    from .git_command     import is_git_command_available
    from .uv_command      import is_uv_command_available
    from .docker_command  import is_docker_command_available
    from .docker_hub_server import is_docker_hub_server_available
    from .pypi_server     import is_pypi_server_available
    from .deployer_extensions import _extensions_installed
    _COMPONENT_AVAIL["network"]          = is_network_available
    _COMPONENT_AVAIL["git-command"]      = is_git_command_available
    _COMPONENT_AVAIL["uv-command"]       = is_uv_command_available
    _COMPONENT_AVAIL["docker-command"]   = is_docker_command_available
    _COMPONENT_AVAIL["docker-hub-server"] = is_docker_hub_server_available
    _COMPONENT_AVAIL["pypi-server"]      = is_pypi_server_available
    _COMPONENT_AVAIL["extensions"]       = _extensions_installed


def component_available(name: str, _seen: set[str] | None = None) -> bool:
    """Return True if *name* and all its transitive deps in _COMPONENT_DEPS are available."""
    _init_component_avail()
    if _seen is None:
        _seen = set()
    if name in _seen:
        return True
    _seen.add(name)
    for dep in _COMPONENT_DEPS.get(name, []):
        if not component_available(dep, _seen):
            return False
    fn = _COMPONENT_AVAIL.get(name)
    return fn() if fn else True


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
        dep
        for deps in _COMPONENT_OPTIONAL_DEPS.values()
        for dep in deps
    }
    _required_set = {
        dep
        for deps in _COMPONENT_DEPS.values()
        for dep in deps
    }
    if name in _optional_set and name not in _required_set:
        return "opt"
    if name in _COMPONENT_KIND:
        return _COMPONENT_KIND[name][0]
    from .plugin import _REGISTRY
    for p in _REGISTRY:
        if p.name == name:
            return p.kind
    return ""


def dep_fix_label(name: str) -> str | None:
    """Return the HeuristicStep label for restoring this dep component's availability, or None."""
    entry = _COMPONENT_KIND.get(name)
    return entry[1] if entry is not None else None


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


def _topo_sorted(components: list[str]) -> list[str]:
    """Return components sorted in topological dependency order via DFS."""
    comp_set = set(components)
    visited: set[str] = set()
    result: list[str] = []

    def visit(name: str) -> None:
        if name in visited:
            return
        visited.add(name)
        for dep in _COMPONENT_DEPS.get(name, []):
            if dep in comp_set:
                visit(dep)
        result.append(name)

    for comp in components:
        visit(comp)
    return result


def _is_visible(name: str) -> bool:
    pred = _COMPONENT_VISIBLE.get(name)
    if pred is not None and not pred():
        return False
    from .role import detect_roles, role_components
    roles, _ = detect_roles()
    active = role_components(roles)
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


def _section_header(title: str) -> str:
    return click.style(f"  {title}", bold=True)


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


def _collect_img_status(visible: list[str]) -> dict[str, bool]:
    """Return {comp: image_built} for components with a registered Docker image."""
    from ._build import _BUILD_REGISTRY
    result: dict[str, bool] = {}
    for comp in visible:
        if comp in _BUILD_REGISTRY:
            _, is_built = _BUILD_REGISTRY[comp]
            if is_built is not None:
                try:
                    result[comp] = is_built()
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
    External infrastructure components (network, git-command, git-repos-access,
    docker, extensions) are hidden when available; use --verbose to show all.
    """
    from ._env import dot_jejune
    from .plugin import _REGISTRY
    from .role import detect_role, detect_roles, role_components

    active_role, _ = detect_role()
    active_roles, _ = detect_roles()
    active_components = role_components(active_roles)

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
    visible_components = _topo_sorted(visible_components)

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

    avail_rows = _build_avail_rows(avail_results, visible_components)

    _CONFIG_NOTE = "  Configuration files: .jejune/env-config · .jejune/env-secrets"

    role_label = f" [{active_role}]" if active_role else ""
    click.echo(click.style(f"jejune doctor{role_label}", bold=True))
    click.echo()

    if not verbose:
        avail_ok = {comp for comp, status, _, _ in avail_rows if status == "ok"}
        config_rows = [
            row for row in config_rows
            if row[0] not in _HIDE_WHEN_AVAILABLE or row[0] not in avail_ok
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
