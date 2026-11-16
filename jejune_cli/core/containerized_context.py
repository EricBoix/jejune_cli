"""ContainerizedContext — shared infrastructure bundle for ContComp instances."""

from dataclasses import dataclass

from jejune_cli.component_ext_command_docker import CompCommandDocker
from jejune_cli.component_ext_server_docker_daemon import CompServerDockerDaemon
from jejune_cli.core.containers_cross_process_coordination import ContainerCoordination
from jejune_cli.component_ext_server_git import CompServerGit
from jejune_cli.component_ext_plugin_packages import CompPluginPackages
from jejune_cli.component_ecosystem import CompEcosystem
from jejune_cli.component_git_access import CompGitAccess
from jejune_cli.roles.role_registry import RoleRegistry


@dataclass
class ContainerizedContext:
    docker: CompCommandDocker
    docker_daemon: CompServerDockerDaemon
    coordination: ContainerCoordination
    git_server: CompServerGit
    plugin_packages: CompPluginPackages
    ecosystem: CompEcosystem
    git_access: CompGitAccess
    role_registry: RoleRegistry
