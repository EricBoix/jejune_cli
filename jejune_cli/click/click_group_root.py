from pathlib import Path

import click

from jejune_cli.core.app_context import AppContext
from jejune_cli.click.click_version import version_option
from jejune_cli.plugins.plugin_cli_wiring import load_plugins


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
            # Plugins must be loaded before super().make_context(): Click handles
            # --help (an eager option) inside it and exits there, so help would
            # otherwise be rendered without any plugin.
            load_plugins(extra["obj"])
        return super().make_context(info_name, args, parent=parent, **extra)

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
        if cmd is not None and ctx.obj is not None:
            self._reject_command_of_other_role(ctx.obj, cmd_name)
        return cmd

    @staticmethod
    def _reject_command_of_other_role(app: AppContext, cmd_name: str) -> None:
        """Refuse a role-owned command the active role does not include.

        format_commands only hides such commands from --help: without this check
        they would still be invocable.
        """
        active_role = app.role_registry.detect_role()
        if not active_role:
            return
        plugin_target_roles = {
            plugin.name: plugin.target_role
            for plugin in app.plugin_registry.plugins
            if plugin.target_role
        }
        if cmd_name in plugin_target_roles:
            target_role = plugin_target_roles[cmd_name]
            if app.role_registry.role_inherits(active_role, target_role):
                return
            offering_roles = [target_role]
        else:
            if not app.role_registry.is_role_owned_cli_command(cmd_name):
                return
            if cmd_name in app.role_registry.role_visible_cli_commands(active_role):
                return
            offering_roles = app.role_registry.roles_offering_cli_command(cmd_name)
        raise click.UsageError(
            f"Command '{cmd_name}' exists but is only available to role: "
            f"{', '.join(offering_roles)} (current role: {active_role.name})."
        )

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
        active_role = app.role_registry.detect_role()

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
                (
                    f"jejune {plugin.name}",
                    plugin.group.get_short_help_str(limit=formatter.width),
                )
                for plugin in app.plugin_registry.plugins
                if plugin.target_role == role_name
            ]

        for role_obj in app.role_registry.display_roles_shown_to(active_role):
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
