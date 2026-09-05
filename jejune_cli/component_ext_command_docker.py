"""docker-command component."""
from .component_ext_command import ext_command


class comp_command_docker(ext_command):
    def __init__(self) -> None:
        super().__init__(
            name="docker-command",
            command=["docker", "info"],
            hint="install Docker Desktop (https://docs.docker.com/get-docker/)",
        )
        type(self).registry.add(self)


comp_command_docker()
