import click

from .click_group_root import cli
from .click_aliases import AliasShim, register_aliases
from .click_build import build_cmd
from .plugin_registry import PLUGIN_REGISTRY
from .role_registry import ROLE_REGISTRY
from .click_doctor import availability, doctor
from .click_next_steps import next_cmd
from .click_role_registry import role
from .click_convert import convert
from .plugin_description import plugin_description as _PluginDescription
from .click_comp_deployment import deployment
from .click_comp_ecosystem import ecosystem
from .click_components import components
from .click_plugin_package_catalog import plugin_packages_group
from .click_group_configuration import (
    configuration,
    register_role_config_subgroup,
)
from .click_containers import containers_cli
from .click_cont_comp_graph import graph
from .click_llm import llm
from .click_manifest import manifest
from .click_llm_observability import llm_observability
from .click_cont_comp_neo4j import neo4j


# ---------------------------------------------------------------------------
# CLI entry point and wiring
# ---------------------------------------------------------------------------

document = click.Group("document", help="Document workspace commands.")

cli.add_command(configuration)
cli.add_command(components)
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

cli.aliases = register_aliases(cli, document)


# ---------------------------------------------------------------------------
# Plugin loading
# ---------------------------------------------------------------------------


def _handle_plugin(plugin: "_PluginDescription") -> None:
    cli.add_command(plugin.group, plugin.name)
    if plugin.role is not None:
        ROLE_REGISTRY.register_from_plugin(plugin.role)
        if plugin.role.config_group is not None:
            register_role_config_subgroup(plugin.role.config_group)


PLUGIN_REGISTRY.add_post_hook(_handle_plugin)
if ROLE_REGISTRY.detect_role():
    PLUGIN_REGISTRY.load_all()
