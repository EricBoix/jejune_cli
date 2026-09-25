"""Assembly: import all built-in component constructors and wire them into REGISTRY."""

from .component_registry import ComponentRegistry
from .component_ext_command_docker import DOCKER_COMMAND
from .component_ext_network import comp_network
from .component_ext_command_git import comp_command_git
from .component_ext_server_docker_daemon import comp_server_docker_daemon
from .component_ext_command_uv import comp_command_uv
from .component_ext_server_pypi import comp_server_pypi
from .component_ext_server_docker_hub import comp_server_docker_hub
from .component_ext_server_git import comp_server_git
from .component_ext_server_llm import comp_server_llm
from .component_ext_server_llm_observability import comp_server_llm_observability
from .component_ext_plugin_packages import comp_plugin_packages
from .component_ecosystem import comp_ecosystem
from .component_catalog import comp_catalog
from .component_manifest import comp_manifest
from .component_cont_convert import comp_convert
from .component_cont_neo4j import comp_neo4j
from .component_cont_graph import comp_graph
from .component_cont_neo4j_to_rdf_ttl import comp_neo4j_to_rdf_ttl
from .component_deployment import comp_deployment
_registry = ComponentRegistry()
_registry._comps.append(comp_network())
_registry._comps.append(comp_command_git())
_registry._comps.append(DOCKER_COMMAND)
_registry._comps.append(comp_server_docker_daemon())
_registry._comps.append(comp_command_uv())
_registry._comps.append(comp_server_pypi())
_registry._comps.append(comp_server_docker_hub())
_registry._comps.append(comp_server_git())
_registry._comps.append(comp_server_llm())
_registry._comps.append(comp_server_llm_observability())
_registry._comps.append(comp_plugin_packages())
_registry._comps.append(comp_ecosystem())
_registry._comps.append(comp_catalog())
_registry._comps.append(comp_manifest())
_registry._comps.append(comp_convert())
_registry._comps.append(comp_neo4j())
_registry._comps.append(comp_graph())
_registry._comps.append(comp_neo4j_to_rdf_ttl())
_registry._comps.append(comp_deployment())
_registry._sort()
_registry.validate()

REGISTRY: ComponentRegistry = _registry
