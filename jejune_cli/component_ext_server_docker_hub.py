"""Docker Hub registry component."""

import subprocess

from .component_with_config import ConfComp


class CompServerDockerHub(ConfComp):
    """Represents the Docker Hub public registry.

    Depends on network (internet reachability) and docker-command (the CLI
    used to pull images).  Availability is verified via ``docker info``:
    if the Docker daemon is running and has Docker Hub configured as its
    index server, images can be pulled.
    """

    def __init__(self, network, docker_command) -> None:
        super().__init__(
            name="docker-hub-server",
            dependencies=[network, docker_command],
            hint="check network connectivity and that Docker Desktop is running",
        )

    def check(self) -> tuple[str, str]:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.IndexServerAddress}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return "error", "docker info failed — Docker daemon not running"
        address = result.stdout.strip()
        if not address:
            return "error", "Docker Hub index server address not found in docker info"
        return "ok", ""
