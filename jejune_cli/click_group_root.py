from pathlib import Path

import click

from .app_context import AppContext
from .click_version import version_option
from .plugin_cli_wiring import load_plugins


class _RootClickGroup(click.Group):
    """Root CLI group — real application entry point.

    make_context() is the first Click hook called on every invocation (including
    --help).  It bootstraps AppContext, which constructs all registries and wires
    all components, before any command callback or help formatter runs.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aliases: list = []

    def make_context(self, info_name, args, parent=None, **extra):
        ctx = super().make_context(info_name, args, parent=parent, **extra)
        if ctx.obj is None:
            ctx.obj = AppContext(cli=self)
            load_plugins(ctx.obj)
        return ctx

    def invoke(self, ctx: click.Context) -> object:
        # invoked_subcommand is set inside Group.invoke(), so read it after.
        try:
            result = super().invoke(ctx)
        except SystemExit as exc:
            if exc.code == 0 and ctx.invoked_subcommand != "next":  # skip on error exit
                ctx.obj.heuristic_step_registry.print_next_steps()
            raise
        if ctx.invoked_subcommand != "next":
            ctx.obj.heuristic_step_registry.print_next_steps()
        return result

    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        app = ctx.obj
        active_role = app.role_registry.detect_role_name() if app else None
        prefix = (
            f"Usage [{active_role}]: "
            if active_role and app and active_role in app.role_registry.roles
            else "Usage: "
        )
        formatter.write_usage(
            ctx.command_path, "[OPTIONS] COMPONENT COMMAND [ARGS]...", prefix=prefix
        )

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        app = ctx.obj
        if app is None:
            return
        active_role = app.role_registry.detect_role_name()

        app.component_registry.load_all_configurations(Path.cwd())

        _hidden_unless_configured = {
            "convert": lambda: app.component_registry.get(
                "convert"
            ).configuration.check()[0]
            == "ok"
            or Path.cwd().joinpath("full-catalog.yaml").exists(),
            "next": lambda: app.heuristic_step_registry.has_heuristics_for_role(
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
                for p in app.plugin_registry.plugins
                if p.target_role == role_name
            ]

        for role_obj in app.role_registry.display_roles:
            if (
                active_role in app.role_registry.roles
                and not app.role_registry.role_inherits(active_role, role_obj.name)
            ):
                continue
            rows = _rows(app.role_registry.role_cli_commands(role_obj))
            rows += _plugin_rows(role_obj.name)
            rows += [
                (f"jejune {name}", f"alias for: jejune {canonical}")
                for grp, name, _, canonical, alias_role in self.aliases
                if alias_role == role_obj.name and grp is self
            ]
            if rows:
                with formatter.section(app.role_registry.section_title(role_obj.name)):
                    formatter.write_dl(rows)


@click.group(cls=_RootClickGroup)
@version_option
def cli():
    """jejune — jejuneness workflow CLI.

    Run `jejune configuration <role> init` to set up a new workspace.
    """
