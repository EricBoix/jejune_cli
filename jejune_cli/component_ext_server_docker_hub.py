"""Docker Hub registry component."""

import subprocess

from .component_with_config import ConfComp


class CompServerDockerHub(ConfComp):
    """Represents the Docker Hub public registry.

    Depends on network (internet reachability), docker-command (the CLI
    used to pull images) and docker-daemon (which serves the pulls).
    Availability is verified via ``docker info``:
    if the Docker daemon is running and has Docker Hub configured as its
    index server, images can be pulled.
    """

    def __init__(self, network, docker_command, docker_daemon) -> None:
        super().__init__(
            name="docker-hub-server",
            dependencies=[network, docker_command, docker_daemon],
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
            # "docker info --format" exits 0 with empty output when the daemon is down
            return (
                "error",
                "Docker Hub index server address not found in docker info"
                " (is the Docker daemon running?)",
            )
        return "ok", ""
