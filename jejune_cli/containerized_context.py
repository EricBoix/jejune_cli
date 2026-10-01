"""ContainerizedContext — shared infrastructure bundle for ContComp instances."""

from dataclasses import dataclass

from .component_ext_command_docker import CompCommandDocker
from .component_ext_server_docker_daemon import CompServerDockerDaemon
from .containers_cross_process_coordination import ContainerCoordination
from .component_ext_server_git import CompServerGit
from .component_ext_plugin_packages import CompPluginPackages
from .component_ecosystem import CompEcosystem


@dataclass
class ContainerizedContext:
    docker: CompCommandDocker
    docker_daemon: CompServerDockerDaemon
    coordination: ContainerCoordination
    git_server: CompServerGit
    plugin_packages: CompPluginPackages
    ecosystem: CompEcosystem
