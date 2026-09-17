from pathlib import Path

import click

from .click_version import version_option
from .component_registry import REGISTRY as _COMP_REGISTRY
from .heuristic_step_registry import HEURISTIC_STEP_REGISTRY
from .plugin_registry import PLUGIN_REGISTRY
from .role_registry import ROLE_REGISTRY


class _RootClickGroup(click.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aliases: list = []

    def invoke(self, ctx: click.Context) -> object:
        cmd_name = ctx._protected_args[0] if ctx._protected_args else None
        try:
            result = super().invoke(ctx)
        except SystemExit as exc:
            if exc.code == 0 and cmd_name != "next":
                HEURISTIC_STEP_REGISTRY.print_next_steps()
            raise
        if cmd_name != "next":
            HEURISTIC_STEP_REGISTRY.print_next_steps()
        return result

    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        active_role = ROLE_REGISTRY.detect_role_name()
        prefix = (
            f"Usage [{active_role}]: "
            if active_role in ROLE_REGISTRY.roles
            else "Usage: "
        )
        formatter.write_usage(
            ctx.command_path, "[OPTIONS] COMPONENT COMMAND [ARGS]...", prefix=prefix
        )

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        active_role = ROLE_REGISTRY.detect_role_name()

        for comp in _COMP_REGISTRY:
            if hasattr(comp, "configuration"):
                comp.configuration.load(Path.cwd())

        _hidden_unless_configured = {
            "convert": lambda: _COMP_REGISTRY.get("convert").configuration.check()[0]
            == "ok"
            or Path.cwd().joinpath("full-catalog.yaml").exists(),
            "next": lambda: HEURISTIC_STEP_REGISTRY.has_heuristics_for_role(
                active_role
            ),
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
            return [row for name in names if (row := _row(name))]

        def _plugin_rows(role_name: str) -> list[tuple[str, str]]:
            return [
                (f"jejune {p.name}", p.group.get_short_help_str(limit=formatter.width))
                for p in PLUGIN_REGISTRY.plugins
                if p.target_role == role_name
            ]

        _included = set(ROLE_REGISTRY.includes(active_role))
        for role_obj in ROLE_REGISTRY.display_roles:
            if (
                active_role in ROLE_REGISTRY.roles
                and role_obj.name not in {active_role} | _included
            ):
                continue
            rows = _rows(role_obj.cli_commands)
            rows += _plugin_rows(role_obj.name)
            rows += [
                (f"jejune {name}", f"alias for: jejune {canonical}")
                for grp, name, _, canonical, alias_role in self.aliases
                if alias_role == role_obj.name and grp is self
            ]
            if rows:
                with formatter.section(ROLE_REGISTRY.section_title(role_obj.name)):
                    formatter.write_dl(rows)


@click.group(cls=_RootClickGroup)
@version_option
def cli():
    """jejune — jejuneness workflow CLI.

    Run `jejune configuration <role> init` to set up a new workspace.
    """
