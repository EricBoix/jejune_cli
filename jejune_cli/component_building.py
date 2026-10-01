"""Explicit component wiring — called by AppContext.__init__."""

from __future__ import annotations

from .component_registry import ComponentRegistry
from .component_containerized import ContComp
from .containerized_context import ContainerizedContext
from .component_ext_command_docker import comp_command_docker
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
from .containers_cross_process_coordination import ContainerCoordination
from .plugin_package_catalog import plugin_package_catalog
from .plugin_registry import PluginRegistry
from .role_registry import RoleRegistry


def build_components(
    registry: ComponentRegistry,
    coordination: ContainerCoordination,
    role_registry: RoleRegistry,
    plugin_registry: PluginRegistry,
) -> ContainerizedContext:
    """Instantiate all built-in components with explicit dependencies and register them."""
    catalog = plugin_package_catalog(registry, role_registry, plugin_registry)

    # Ext command components
    docker_command = comp_command_docker()
    git_command = comp_command_git()
    uv_command = comp_command_uv()

    # Ext components with no upstream deps
    docker_daemon = comp_server_docker_daemon()
    network = comp_network()

    # Ext server components that depend on network
    pypi_server = comp_server_pypi(network=network)
    docker_hub = comp_server_docker_hub(network=network)
    git_server = comp_server_git(network=network, git_command=git_command)
    llm = comp_server_llm(network=network)

    # Higher-level ext components
    ecosystem = comp_ecosystem(
        git_server=git_server,
        role_registry=role_registry,
        plugin_registry=plugin_registry,
    )
    catalog_comp = comp_catalog(ecosystem=ecosystem)
    manifest = comp_manifest()
    plugin_packages = comp_plugin_packages(
        git_server=git_server, uv_command=uv_command, catalog=catalog
    )

    # Register runtime dependencies (policy providers, excluded from topology)
    network.set_runtime_dependency("ecosystem", ecosystem)
    git_command.set_runtime_dependency("ecosystem", ecosystem)

    # Bundle shared infrastructure; set class-level fallback for plugin ContComp subclasses
    context = ContainerizedContext(
        docker=docker_command,
        docker_daemon=docker_daemon,
        coordination=coordination,
        git_server=git_server,
        plugin_packages=plugin_packages,
        ecosystem=ecosystem,
    )
    ContComp.set_shared_context(context)

    # Cont components
    llm_obs = comp_server_llm_observability(context=context)
    neo4j = comp_neo4j(git_server=git_server, docker_hub=docker_hub, context=context)
    graph = comp_graph(
        git_server=git_server,
        neo4j=neo4j,
        llm=llm,
        llm_observability=llm_obs,
        context=context,
    )
    convert = comp_convert(pypi_server=pypi_server, context=context)
    neo4j_to_rdf_ttl = comp_neo4j_to_rdf_ttl(
        git_server=git_server, docker_hub=docker_hub, context=context
    )
    deployment = comp_deployment(
        network=network,
        catalog_comp=catalog_comp,
        docker_daemon=docker_daemon,
        docker_command=docker_command,
        plugin_registry=plugin_registry,
        ecosystem=ecosystem,
    )

    for comp in [
        network,
        git_command,
        docker_command,
        docker_daemon,
        uv_command,
        pypi_server,
        docker_hub,
        git_server,
        llm,
        llm_obs,
        plugin_packages,
        ecosystem,
        catalog_comp,
        manifest,
        convert,
        neo4j,
        graph,
        neo4j_to_rdf_ttl,
        deployment,
    ]:
        registry.add(comp)

    registry.validate()
    return context
