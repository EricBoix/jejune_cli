"""Shared configuration utilities and the `jejune configuration` command group."""

import os
from pathlib import Path

import click

from .configuration_doc_steward import (
    CONFIG_GROUPS as _DS_CONFIG_GROUPS,
    COMPONENT_CONFIG_HINTS as _DS_HINTS,
    init as _doc_steward_init,
)
from .configuration_catalog_curator import (
    CONFIG_GROUPS as _CC_CONFIG_GROUPS,
    COMPONENT_CONFIG_HINTS as _CC_HINTS,
    init as _curator_init,
)
from .configuration_deployer import (
    CONFIG_GROUPS as _DEP_CONFIG_GROUPS,
    COMPONENT_CONFIG_HINTS as _DEP_HINTS,
    init as _deployer_init,
)

CONFIG_GROUPS: dict[str, tuple[list[str], str]] = {
    **_DS_CONFIG_GROUPS,
    **_CC_CONFIG_GROUPS,
    **_DEP_CONFIG_GROUPS,
}
COMPONENT_CONFIG_HINTS: dict[str, str] = {
    **_DS_HINTS,
    **_CC_HINTS,
    **_DEP_HINTS,
}

_PLACEHOLDER = "_CHANGE_ME"

_STATUS_DISPLAY: dict[str, tuple[str, str]] = {
    "ok":    ("ok",             "green"),
    "warn":  ("not configured", "yellow"),
    "error": ("error",          "red"),
}


def print_config_table(
    rows: list[tuple[str, str, str, str]],
    hint_header: str = "Hint",
    note: str | None = None,
) -> None:
    """Render Component configuration | Status | Check | <hint_header> table.

    When *note* is given a bottom divider is added followed by the note line.
    """
    if not rows:
        return
    _W_C = max(len("Component configuration"), max(len(r[0]) for r in rows))
    _W_S = max(len("Status"), max(len(_STATUS_DISPLAY.get(r[1], (r[1], ""))[0]) for r in rows))
    _W_K = max(len("Check"), max(len(r[2]) for r in rows))
    _W_H = max(len(hint_header), max(len(r[3]) for r in rows))
    divider = "  " + "─" * (_W_C + 2 + _W_S + 2 + _W_K + 2 + _W_H)
    click.echo(f"  {'Component configuration':<{_W_C}}  {'Status':<{_W_S}}  {'Check':<{_W_K}}  {hint_header}")
    click.echo(divider)
    for comp, status, check, hint in rows:
        text, fg = _STATUS_DISPLAY.get(status, (status, "white"))
        click.echo(f"  {comp:<{_W_C}}  {click.style(f'{text:<{_W_S}}', fg=fg)}  {check:<{_W_K}}  {hint}")
    if note is not None:
        click.echo(divider)
        click.echo(note)


def print_two_col_table(rows: list[tuple[str, str]], col1: str, col2: str) -> None:
    """Render a two-column table; rows may contain pre-styled strings."""
    _W_C = max(len(col1), max(len(click.unstyle(r[0])) for r in rows))
    _W_V = max(len(col2), max(len(click.unstyle(r[1])) for r in rows))
    click.echo(f"  {col1:<{_W_C}}  {col2}")
    click.echo("  " + "─" * (_W_C + 2 + _W_V))
    for c, v in rows:
        pad = " " * (_W_C - len(click.unstyle(c)))
        click.echo(f"  {c}{pad}  {v}")


def _convert_config_status() -> tuple[str, str]:
    """Return (status, raw_msg) for convert configuration."""
    val = os.environ.get("CONVERT_DOC_DIR")
    if not val or _PLACEHOLDER in val:
        return "warn", "CONVERT_DOC_DIR not configured"
    p = Path(val)
    if p.is_file():
        if not p.exists():
            return "error", f"Dockerfile not found at {p.resolve()}"
        return "ok", ""
    ctx = p / "DockerContext"
    if not ctx.is_dir():
        return "error", f"DockerContext not found at {ctx}"
    return "ok", ""


def component_config_check(component: str) -> tuple[str, str]:
    """Return (status, hint) for a component's configuration.

    For components with no required env vars the status is always "ok".
    """
    if component == "convert":
        status, msg = _convert_config_status()
        if status == "ok":
            return "ok", ""
        if status == "error":
            return status, msg
        return status, get_config_hint("convert", status, msg)
    if component not in CONFIG_GROUPS:
        return "ok", ""
    keys, _ = CONFIG_GROUPS[component]
    status, msg = check_config_group(keys)
    return status, get_config_hint(component, status, msg)


def get_config_hint(component: str, status: str, message: str) -> str:  # noqa: ARG001
    """Return the configuration hint for a component given its status."""
    return COMPONENT_CONFIG_HINTS.get(component, "")


def print_config_check(component: str) -> None:
    """Print detailed per-variable config check for a component."""
    if component not in CONFIG_GROUPS:
        click.echo(click.style("no configuration required", fg="green"))
        return
    keys, _ = CONFIG_GROUPS[component]
    _W = max(len(k) for k in keys)
    any_error = False
    for key in keys:
        val = os.environ.get(key)
        if val is None:
            label = click.style("not set", fg="yellow")
        elif _PLACEHOLDER in val:
            label = click.style("placeholder", fg="red")
            any_error = True
        else:
            label = click.style("ok", fg="green")
        click.echo(f"  {key:<{_W}}  {label}")
    if any_error:
        raise SystemExit(1)


def print_config_hint(component: str) -> None:
    """Print the configuration hint for a component."""
    _, hint = component_config_check(component)
    if hint:
        click.echo(hint)
    else:
        click.echo(click.style("no configuration required", fg="green"))


def print_config_status(component: str) -> None:
    """Print configuration status for a component; exit 1 on error."""
    status, hint = component_config_check(component)
    if status == "ok":
        click.echo(click.style("configured", fg="green"))
    elif status == "warn":
        click.echo(f"{click.style('not configured', fg='yellow')}  {hint}")
    else:
        click.echo(f"{click.style('error', fg='red')}  {hint}")
        raise SystemExit(1)


def check_config_group(keys: list[str]) -> tuple[str, str]:
    """Check a group of env vars; return (status, message).

    status is "ok", "warn" (none set — use case not configured), or "error"
    (partial or placeholder values present).
    """
    states: list[tuple[str, str]] = []
    for key in keys:
        val = os.environ.get(key)
        if val is None:
            states.append((key, "missing"))
        elif _PLACEHOLDER in val:
            states.append((key, "placeholder"))
        else:
            states.append((key, "ok"))

    if all(s == "ok" for _, s in states):
        return "ok", "ok"
    if all(s == "missing" for _, s in states):
        return "warn", "not configured"
    issues = [f"{k}: {s}" for k, s in states if s != "ok"]
    return "error", "; ".join(issues)


_ROLE_SUBGROUP_NAMES = frozenset({"doc-steward", "deployer", "catalog-curator"})


_ROLE_CTX_KEY = "_jejune_configuration_role"


class _ConfigurationGroup(click.Group):
    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        from .role import detect_role, ROLES
        active_role, _ = detect_role()
        ctx.meta[_ROLE_CTX_KEY] = active_role

        if active_role in ROLES:
            formatter.write_usage(
                ctx.command_path,
                " ".join(self.collect_usage_pieces(ctx)),
                prefix=f"Usage [{active_role}]: ",
            )
            self.format_help_text(ctx, formatter)
            self.format_options(ctx, formatter)  # calls format_commands internally
            self.format_epilog(ctx, formatter)
        else:
            self.format_commands(ctx, formatter)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        from .role import ROLES
        active_role = ctx.meta.get(_ROLE_CTX_KEY)

        regular: list[tuple[str, str]] = []
        roles: list[tuple[str, str]] = []
        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is None or getattr(cmd, "hidden", False):
                continue
            entry = (name, cmd.get_short_help_str(limit=formatter.width))
            if name in _ROLE_SUBGROUP_NAMES:
                roles.append(entry)
            else:
                regular.append(entry)

        if regular and active_role in ROLES:
            with formatter.section("Commands"):
                formatter.write_dl(regular)

        if roles and active_role not in ROLES:
            formatter.write_paragraph()
            formatter.write_usage(
                "jejune configuration",
                "ROLE init",
                prefix="Usage [all roles]: ",
            )
            with formatter.indentation():
                formatter.write_text("Set jejune role and initialise workspace accordingly.")
                with formatter.section("Roles"):
                    formatter.write_dl(roles)


@click.group(cls=_ConfigurationGroup, short_help="Manage the .jejune/ configuration")
def configuration():
    """Manage the .jejune/ configuration (env-config, env-secrets, catalog.yaml)."""


@click.group("doc-steward", short_help="Doc-steward role workspace")
def _doc_steward_group():
    """Initialise and inspect the doc-steward workspace."""


_doc_steward_group.add_command(_doc_steward_init, "init")


@click.group("deployer", short_help="Deployer role workspace")
def _deployer_group():
    """Initialise and inspect the deployer workspace."""


_deployer_group.add_command(_deployer_init, "init")


@click.group("catalog-curator", short_help="Catalog-curator role workspace")
def _curator_group():
    """Initialise and inspect the catalog-curator workspace."""


_curator_group.add_command(_curator_init, "init")


configuration.add_command(_doc_steward_group)
configuration.add_command(_deployer_group)
configuration.add_command(_curator_group)


@configuration.command("check-config")
def check():
    """Verify configuration variables by component group.

    Reports each group (neo4j, llm) independently:\n
      ok             — all vars set and non-placeholder\n
      not configured — none set (use case not activated, not an error)\n
      error          — partial or placeholder values (needs attention)\n

    Checks os.environ, which already includes values loaded from
    .jejune/env-config and .jejune/env-secrets at startup.
    """
    from .role import detect_role, role_components
    role, _ = detect_role()
    visible = role_components(role)
    groups = {g: v for g, v in CONFIG_GROUPS.items() if visible is None or g in visible}

    if not groups:
        click.echo(click.style("no configuration required for the current role", fg="green"))
        return

    rows = [
        (group, status, msg if status == "error" else "", COMPONENT_CONFIG_HINTS.get(group, "") if status != "ok" else "")
        for group, (keys, _) in groups.items()
        for status, msg in [check_config_group(keys)]
    ]
    print_config_table(rows)
    if any(status == "error" for _, status, _, _ in rows):
        raise SystemExit(1)


configuration.add_command(check, "summary")


def _role_groups() -> dict:
    """Return CONFIG_GROUPS filtered to the currently detected role."""
    from .role import detect_role, role_components
    role, _ = detect_role()
    visible = role_components(role)
    return {g: v for g, v in CONFIG_GROUPS.items() if visible is None or g in visible}


@configuration.command("status-config")
def configuration_status():
    """Per-component configuration status."""
    groups = _role_groups()
    if not groups:
        click.echo(click.style("no configuration required for the current role", fg="green"))
        return
    styled = [
        (comp, click.style(text, fg=fg))
        for comp, st in [(g, check_config_group(keys)[0]) for g, (keys, _) in groups.items()]
        for text, fg in [_STATUS_DISPLAY.get(st, (st, "white"))]
    ]
    print_two_col_table(styled, "Component configuration", "Status")


@configuration.command("hint-config")
def configuration_hint():
    """Configuration hints for non-ok components."""
    groups = _role_groups()
    items = [(group, check_config_group(keys)[0]) for group, (keys, _) in groups.items()]
    rows = [(comp, COMPONENT_CONFIG_HINTS.get(comp, "")) for comp, status in items if status != "ok"]
    rows = [(c, h) for c, h in rows if h]
    if not rows:
        click.echo(click.style("all components configured", fg="green"))
        return
    print_two_col_table(rows, "Component configuration", "Hint")
