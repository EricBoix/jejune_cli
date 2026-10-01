"""Explicit component wiring — called by AppContext.__init__."""

from __future__ import annotations

from .component_registry import ComponentRegistry
from .component_containerized import ContComp
from .containerized_context import ContainerizedContext
from .component_ext_command_docker import CompCommandDocker
from .component_ext_network import CompNetwork
from .component_ext_command_git import CompCommandGit
from .component_ext_server_docker_daemon import CompServerDockerDaemon
from .component_ext_command_uv import CompCommandUv
from .component_ext_server_pypi import CompServerPypi
from .component_ext_server_docker_hub import CompServerDockerHub
from .component_ext_server_git import CompServerGit
from .component_ext_server_llm import CompServerLlm
from .component_ext_server_llm_observability import CompServerLlmObservability
from .component_ext_plugin_packages import CompPluginPackages
from .component_ecosystem import CompEcosystem
from .component_catalog import CompCatalog
from .component_manifest import CompManifest
from .component_cont_convert import CompConvert
from .component_cont_neo4j import CompNeo4j
from .component_cont_graph import CompGraph
from .component_cont_neo4j_to_rdf_ttl import CompNeo4jToRdfTtl
from .component_deployment import CompDeployment
from .containers_cross_process_coordination import ContainerCoordination
from .plugin_package_catalog import PluginPackageCatalog
from .plugin_registry import PluginRegistry
from .role_registry import RoleRegistry


def build_components(
    registry: ComponentRegistry,
    coordination: ContainerCoordination,
    role_registry: RoleRegistry,
    plugin_registry: PluginRegistry,
) -> ContainerizedContext:
    """Instantiate all built-in components with explicit dependencies and register them."""
    catalog = PluginPackageCatalog(registry, role_registry, plugin_registry)

    # Ext command components
    docker_command = CompCommandDocker()
    git_command = CompCommandGit()
    uv_command = CompCommandUv()

    # Ext components with no upstream deps
    docker_daemon = CompServerDockerDaemon()
    network = CompNetwork()

    # Ext server components that depend on network
    pypi_server = CompServerPypi(network=network)
    docker_hub = CompServerDockerHub(network=network)
    git_server = CompServerGit(network=network, git_command=git_command)
    llm = CompServerLlm(network=network)

    # Higher-level ext components
    ecosystem = CompEcosystem(
        git_server=git_server,
        role_registry=role_registry,
        plugin_registry=plugin_registry,
    )
    catalog_comp = CompCatalog(ecosystem=ecosystem)
    manifest = CompManifest()
    plugin_packages = CompPluginPackages(
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
    llm_obs = CompServerLlmObservability(context=context)
    neo4j = CompNeo4j(git_server=git_server, docker_hub=docker_hub, context=context)
    graph = CompGraph(
        git_server=git_server,
        neo4j=neo4j,
        llm=llm,
        llm_observability=llm_obs,
        context=context,
    )
    convert = CompConvert(pypi_server=pypi_server, context=context)
    neo4j_to_rdf_ttl = CompNeo4jToRdfTtl(
        git_server=git_server, docker_hub=docker_hub, context=context
    )
    deployment = CompDeployment(
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
