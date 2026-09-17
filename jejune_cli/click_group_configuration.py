"""Shared configuration utilities and the `jejune configuration` command group."""

import click

from .click_doctor import (
    config_check_availability,
    config_hint_availability,
    config_status_availability,
)
from .click_helpers import print_two_col_table
from .click_workspace_doc_steward import doc_steward_group as _doc_steward_group
from .click_workspace_deployer import deployer_group as _deployer_group
from .click_theme import ClickTheme


def register_role_config_subgroup(group: click.Group) -> None:
    """Add a role-specific init subgroup to ``jejune configuration``."""
    group._role_subgroup = True
    configuration.add_command(group)


class _ConfigurationGroup(click.Group):
    _ROLE_CTX_KEY = "_jejune_configuration_role"

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        from .role_registry import ROLE_REGISTRY
        active_role = ROLE_REGISTRY.detect_role()
        ctx.meta[self._ROLE_CTX_KEY] = active_role

        if active_role:
            formatter.write_usage(
                ctx.command_path,
                " ".join(self.collect_usage_pieces(ctx)),
                prefix=f"Usage [{active_role.name}]: ",
            )
            self.format_help_text(ctx, formatter)
            self.format_options(ctx, formatter)  # calls format_commands internally
            self.format_epilog(ctx, formatter)
        else:
            self.format_commands(ctx, formatter)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        active_role = ctx.meta.get(self._ROLE_CTX_KEY)

        regular: list[tuple[str, str]] = []
        roles: list[tuple[str, str]] = []
        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is None or getattr(cmd, "hidden", False):
                continue
            entry = (name, cmd.get_short_help_str(limit=formatter.width))
            if getattr(cmd, '_role_subgroup', False):
                roles.append(entry)
            else:
                regular.append(entry)

        if regular and active_role is not None:
            with formatter.section("Commands"):
                formatter.write_dl(regular)

        if roles and not active_role:
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
        elif roles:
            with formatter.section("Roles"):
                formatter.write_dl(roles)


@click.group(cls=_ConfigurationGroup, short_help="Manage the .jejune/ configuration")
def configuration():
    """Manage the .jejune/ configuration (env-config, env-secrets)."""


def _print_config_table(
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
    _W_S = max(len("Status"), max(len(ClickTheme.status_icons.get(r[1], (r[1], ""))[0]) for r in rows))
    _W_K = max(len("Check"), max(len(r[2]) for r in rows))
    _W_H = max(len(hint_header), max(len(r[3]) for r in rows))
    divider = "  " + "─" * (_W_C + 2 + _W_S + 2 + _W_K + 2 + _W_H)
    click.echo(f"  {'Component configuration':<{_W_C}}  {'Status':<{_W_S}}  {'Check':<{_W_K}}  {hint_header}")
    click.echo(divider)
    for comp, status, check, hint in rows:
        text, fg = ClickTheme.status_icons.get(status, (status, "white"))
        click.echo(f"  {comp:<{_W_C}}  {click.style(f'{text:<{_W_S}}', fg=fg)}  {check:<{_W_K}}  {hint}")
    if note is not None:
        click.echo(divider)
        click.echo(note)


def _role_config_checks() -> list[tuple[str, str, str, str]]:
    """Return (name, status, msg, hint) for every configurable component in the current role."""
    from .role_registry import ROLE_REGISTRY
    from .component_registry import REGISTRY as COMP_REGISTRY
    role = ROLE_REGISTRY.detect_role()
    role_components = ROLE_REGISTRY.role_components(role)
    return [
        (comp.name, *comp.configuration.check())
        for comp in COMP_REGISTRY
        if (role_components is None or comp in role_components)
        and hasattr(comp, "configuration")
        and comp.configuration
    ]


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
    checks = _role_config_checks()
    if not checks:
        click.echo(click.style("no configuration required for the current role", fg="green"))
        return
    rows = [
        (name, status, msg if status == "error" else "", hint if status != "ok" else "")
        for name, status, msg, hint in checks
    ]
    _print_config_table(rows)
    if any(status == "error" for _, status, _, _ in rows):
        raise SystemExit(1)


@configuration.command("status-config")
def configuration_status():
    """Per-component configuration status."""
    checks = _role_config_checks()
    if not checks:
        click.echo(click.style("no configuration required for the current role", fg="green"))
        return
    styled = [
        (name, click.style(text, fg=fg))
        for name, status, _, _ in checks
        for text, fg in [ClickTheme.status_icons.get(status, (status, "white"))]
    ]
    print_two_col_table(styled, "Component configuration", "Status")


@configuration.command("hint-config")
def configuration_hint():
    """Configuration hints for non-ok components."""
    rows = [(name, hint) for name, status, _, hint in _role_config_checks() if status != "ok" and hint]
    if not rows:
        click.echo(click.style("all components configured", fg="green"))
        return
    print_two_col_table(rows, "Component configuration", "Hint")


configuration.add_command(_doc_steward_group)
configuration.add_command(_deployer_group)
configuration.add_command(check, "summary")
configuration.add_command(config_check_availability)
configuration.add_command(config_status_availability)
configuration.add_command(config_hint_availability)
