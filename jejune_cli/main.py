from pathlib import Path

import click

from .click_version import version_option
from .click_aliases import AliasShim, register_aliases
from .click_build import build_cmd
from .dot_jejune import dot_jejune
from .component_registry import REGISTRY as _COMP_REGISTRY
from .plugin_registry import PLUGIN_REGISTRY
from .role_registry import ROLE_REGISTRY
from .click_doctor import (
    availability,
    config_check_availability,
    config_hint_availability,
    config_status_availability,
    doctor,
)
from .click_next_steps import next_cmd
from .click_role_registry import role
from .click_convert import convert
from .plugin_description import plugin_description as _PluginDescription
from .click_comp_deployment import deployment
from .click_comp_ecosystem import ecosystem
from .click_components import components
from .click_plugin_package_catalog import plugin_packages_group
from .click_comp_configuration import (
    configuration,
    register_role_config_subgroup,
)
from .click_containers import containers_cli
from .click_cont_comp_graph import graph
from .click_llm import llm
from .click_manifest import manifest
from .click_llm_observability import llm_observability
from .click_cont_comp_neo4j import neo4j
from .heuristic_step_registry import HEURISTIC_STEP_REGISTRY

_ACTIVE_ROLE: str | None = ROLE_REGISTRY.detect_role_name()


def _doctor_viable() -> bool:
    return not (_ACTIVE_ROLE in (None, "doc-steward") and not dot_jejune().is_dir())


HEURISTIC_STEP_REGISTRY.register_command_precondition("jejune doctor", _doctor_viable)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


class _JejuneGroup(click.Group):
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
        prefix = (
            f"Usage [{_ACTIVE_ROLE}]: "
            if _ACTIVE_ROLE in ROLE_REGISTRY.roles
            else "Usage: "
        )
        formatter.write_usage(
            ctx.command_path, "[OPTIONS] COMPONENT COMMAND [ARGS]...", prefix=prefix
        )

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        for _comp in _COMP_REGISTRY:
            if hasattr(_comp, "configuration"):
                _comp.configuration.load(Path.cwd())

        _hidden_unless_configured = {
            "convert": lambda: _COMP_REGISTRY.get("convert").configuration.check()[0]
            == "ok"
            or Path.cwd().joinpath("full-catalog.yaml").exists(),
            "next": lambda: HEURISTIC_STEP_REGISTRY.has_heuristics_for_role(
                _ACTIVE_ROLE
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
            return [r for name in names if (r := _row(name))]

        def _plugin_rows(role_name: str) -> list[tuple[str, str]]:
            return [
                (f"jejune {p.name}", p.group.get_short_help_str(limit=formatter.width))
                for p in PLUGIN_REGISTRY.plugins
                if p.target_role == role_name
            ]

        _included = set(ROLE_REGISTRY.includes(_ACTIVE_ROLE))
        for role_obj in ROLE_REGISTRY.display_roles:
            if (
                _ACTIVE_ROLE in ROLE_REGISTRY.roles
                and role_obj.name not in {_ACTIVE_ROLE} | _included
            ):
                continue
            rows = _rows(role_obj.cli_commands)
            rows += _plugin_rows(role_obj.name)
            rows += [
                (f"jejune {name}", f"alias for: jejune {canonical}")
                for grp, name, _, canonical, alias_role in _ALIASES
                if alias_role == role_obj.name and grp is self
            ]
            if rows:
                with formatter.section(ROLE_REGISTRY.section_title(role_obj.name)):
                    formatter.write_dl(rows)


# ---------------------------------------------------------------------------
# CLI entry point and wiring
# ---------------------------------------------------------------------------

document = click.Group("document", help="Document workspace commands.")


@click.group(cls=_JejuneGroup)
@version_option
def cli():
    """jejune — jejuneness workflow CLI.

    Run `jejune configuration <role> init` to set up a new workspace.
    """


cli.add_command(configuration)
cli.add_command(components)
configuration.add_command(config_check_availability)
configuration.add_command(config_status_availability)
configuration.add_command(config_hint_availability)
cli.add_command(containers_cli)
cli.add_command(neo4j)
cli.add_command(llm)
cli.add_command(llm_observability)
cli.add_command(graph)
cli.add_command(manifest)
cli.add_command(deployment)
cli.add_command(document)
cli.add_command(ecosystem)
cli.add_command(plugin_packages_group, "plugin-packages")
cli.add_command(convert)
cli.add_command(availability)
cli.add_command(doctor)
cli.add_command(role)
cli.add_command(next_cmd, "next")
cli.add_command(build_cmd, "build")

# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------

# _ALIASES is referenced at runtime by _JejuneGroup.format_commands (defined above).
_ALIASES = register_aliases(cli, document)


# ---------------------------------------------------------------------------
# Plugin loading
# ---------------------------------------------------------------------------


def _handle_plugin(plugin: "_PluginDescription") -> None:
    cli.add_command(plugin.group, plugin.name)
    if plugin.role is not None:
        ROLE_REGISTRY.register_from_plugin(plugin.role)
        if plugin.role.config_group is not None:
            register_role_config_subgroup(plugin.role.config_group)


def _finalize_plugins() -> None:
    global _ACTIVE_ROLE
    _ACTIVE_ROLE = ROLE_REGISTRY.detect_role_name()


PLUGIN_REGISTRY.add_post_hook(_handle_plugin)
PLUGIN_REGISTRY.set_finalize_hook(_finalize_plugins)
if ROLE_REGISTRY.detect_role():
    PLUGIN_REGISTRY.load_all()
