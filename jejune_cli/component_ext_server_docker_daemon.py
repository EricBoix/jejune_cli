"""Docker daemon component: checks if the Docker daemon is running."""

import subprocess

from .component_ext import ExtComp


class CompServerDockerDaemon(ExtComp):
    def __init__(self) -> None:
        super().__init__(
            name="docker-daemon",
            hint="start Docker Desktop or the Docker daemon",
        )

    def check(self) -> tuple[str, str]:
        try:
            result = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                timeout=10,
            )
            # "docker info --format" exits 0 even when the daemon is down,
            # hence "docker version" and a check on its output.
            if result.returncode == 0 and result.stdout.strip():
                return "ok", ""
            return "error", "Docker daemon is not running"
        except Exception as exc:
            return "error", f"Docker daemon check failed: {exc}"
