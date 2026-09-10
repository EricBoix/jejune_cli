"""Docker daemon component: checks if the Docker daemon is running."""
import subprocess

from .component_ext import ext_comp
from .component_registry import ComponentRegistry


class comp_server_docker_daemon(ext_comp):
    def __init__(self) -> None:
        super().__init__(
            name="docker-daemon",
            dependencies=[ComponentRegistry().get("docker-command")],
            hint="start Docker Desktop or the Docker daemon",
        )

    def check(self) -> tuple[str, str]:
        try:
            result = subprocess.run(
                ["docker", "stats", "--no-stream"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                return "ok", ""
            return "error", "Docker daemon is not running"
        except Exception as exc:
            return "error", f"Docker daemon check failed: {exc}"
