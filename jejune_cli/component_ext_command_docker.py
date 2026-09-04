"""docker-command component."""
from .component_ext_command import ext_command
from .component_registry import REGISTRY


class comp_command_docker(ext_command):
    def __init__(self) -> None:
        super().__init__(
            name="docker-command",
            command=["docker", "info"],
            hint="install Docker Desktop (https://docs.docker.com/get-docker/)",
        )


REGISTRY.add(comp_command_docker())
