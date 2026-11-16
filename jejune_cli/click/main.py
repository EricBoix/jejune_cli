# cli is an instance of _RootClickGroup; see click_group_root.py for bootstrapping logic.
from jejune_cli.click.click_group_root import cli
from jejune_cli.click.click_group_document import document

# Infrastructure / cross-cutting groups
from jejune_cli.click.click_aliases import register_aliases
from jejune_cli.click.click_group_configuration import configuration
from jejune_cli.click.click_components import components
from jejune_cli.click.containers.click_containers import containers_cli
from jejune_cli.click.click_plugin_package_catalog import plugin_packages_group
from jejune_cli.click.click_role_registry import role, roles

# Top-level commands
from jejune_cli.click.click_build import build_cmd
from jejune_cli.click.click_discover import discover_cmd
from jejune_cli.click.click_doctor import availability
from jejune_cli.click.click_next_steps import next_cmd
from jejune_cli.click.click_update import update_cmd

# Doc-steward component commands
from jejune_cli.click.click_group_llm import llm
from jejune_cli.click.containers.click_cont_comp_oxigraph import oxigraph
from jejune_cli.click.containers.click_cont_comp_llm_observability import (
    llm_observability,
)
from jejune_cli.click.containers.click_cont_comp_neo4j import neo4j
from jejune_cli.click.containers.click_cont_comp_graph import graph
from jejune_cli.click.containers.click_cont_comp_convert import convert
from jejune_cli.click.containers.click_cont_comp_converters import converters
from jejune_cli.click.click_group_manifest import manifest

# Deployer component commands
from jejune_cli.click.click_catalog import catalog_group
from jejune_cli.click.click_group_deployment import deployment
from jejune_cli.click.click_group_ecosystem import ecosystem
from jejune_cli.click.click_group_git_access import git_access

# Infrastructure / cross-cutting groups
cli.add_command(document)
cli.add_command(configuration)
cli.add_command(components)
cli.add_command(containers_cli)
cli.add_command(plugin_packages_group, "plugin-packages")
cli.add_command(role)
cli.add_command(roles)

# Top-level commands
cli.add_command(build_cmd)
cli.add_command(discover_cmd)
cli.add_command(availability)
cli.add_command(next_cmd)
cli.add_command(update_cmd)

# Doc-steward component commands
cli.add_command(neo4j)
cli.add_command(oxigraph)
cli.add_command(llm)
cli.add_command(llm_observability)
cli.add_command(graph)
cli.add_command(convert)
cli.add_command(converters)
cli.add_command(manifest)

# Deployer component commands
cli.add_command(catalog_group, "catalog")
cli.add_command(deployment)
cli.add_command(ecosystem)
cli.add_command(git_access, "git-access")

cli.aliases = register_aliases(cli, document)
