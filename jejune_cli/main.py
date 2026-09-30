# cli is an instance of _RootClickGroup; see click_group_root.py for bootstrapping logic.
from .click_group_root import cli
from .click_group_document import document

# Infrastructure / cross-cutting groups
from .click_aliases import register_aliases
from .click_group_configuration import configuration
from .click_components import components
from .click_containers import containers_cli
from .click_plugin_package_catalog import plugin_packages_group
from .click_role_registry import role

# Top-level commands
from .click_build import build_cmd
from .click_doctor import availability
from .click_next_steps import next_cmd

# Doc-steward component commands
from .click_comp_llm import llm
from .click_cont_comp_llm_observability import llm_observability
from .click_cont_comp_neo4j import neo4j
from .click_cont_comp_graph import graph
from .click_cont_comp_convert import convert
from .click_comp_manifest import manifest

# Deployer component commands
from .click_comp_deployment import deployment
from .click_comp_ecosystem import ecosystem

# Infrastructure / cross-cutting groups
cli.add_command(document)
cli.add_command(configuration)
cli.add_command(components)
cli.add_command(containers_cli)
cli.add_command(plugin_packages_group, "plugin-packages")
cli.add_command(role)

# Top-level commands
cli.add_command(build_cmd)
cli.add_command(availability)
cli.add_command(next_cmd)

# Doc-steward component commands
cli.add_command(neo4j)
cli.add_command(llm)
cli.add_command(llm_observability)
cli.add_command(graph)
cli.add_command(convert)
cli.add_command(manifest)

# Deployer component commands
cli.add_command(deployment)
cli.add_command(ecosystem)

cli.aliases = register_aliases(cli, document)
