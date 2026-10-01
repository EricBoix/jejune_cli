"""ContainerizedContext — shared infrastructure bundle for cont_comp instances."""
from dataclasses import dataclass

from .component_ext_command_docker import comp_command_docker
from .component_ext_server_docker_daemon import comp_server_docker_daemon
from .containers_cross_process_coordination import ContainerCoordination
from .component_ext_server_git import comp_server_git
from .component_ext_plugin_packages import comp_plugin_packages
from .component_ecosystem import comp_ecosystem


@dataclass
class ContainerizedContext:
    docker: comp_command_docker
    docker_daemon: comp_server_docker_daemon
    coordination: ContainerCoordination
    git_server: comp_server_git
    plugin_packages: comp_plugin_packages
    ecosystem: comp_ecosystem
