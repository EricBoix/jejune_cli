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
        # Bootstrap AppContext before super().make_context() so that ctx.obj is
        # available inside get_command() during parse_args() / resolve_command().
        fresh = "obj" not in extra
        if fresh:
            extra["obj"] = AppContext(cli=self)
        ctx = super().make_context(info_name, args, parent=parent, **extra)
        if fresh:
            load_plugins(ctx.obj)
        return ctx

    def invoke(self, ctx: click.Context) -> object:
        # invoked_subcommand is set inside Group.invoke(), so read it after.
        try:
            result = super().invoke(ctx)
        except SystemExit as exc:
            if exc.code == 0:  # skip on error exit
                ctx.obj.heuristic_step_registry.print_next_steps()
            raise
        ctx.obj.heuristic_step_registry.print_next_steps()
        return result

    def get_command(self, ctx: click.Context, cmd_name: str) -> "click.Command | None":
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None and ctx.obj is not None:
            if not ctx.obj.role_registry.detect_role():
                raise click.UsageError(
                    f"No such command '{cmd_name}'. "
                    "Role-specific commands require a recognized workspace."
                )
        return cmd

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

        def _row(name: str) -> tuple[str, str] | None:
            comp = app.component_registry.get(name)
            if hasattr(comp, "is_relevant") and not comp.is_relevant(Path.cwd()):
                return None
            cmd = super(_RootClickGroup, self).get_command(ctx, name)
            if cmd is None or cmd.hidden:
                return None
            if hasattr(cmd, "is_visible") and not cmd.is_visible(app):
                return None
            return (f"jejune {name}", cmd.get_short_help_str(limit=formatter.width))

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
