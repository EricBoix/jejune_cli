"""docker-command component: Docker CLI availability check and operations."""
import subprocess

from .component_ext_command import ext_command


class comp_command_docker(ext_command):
    def __init__(self) -> None:
        super().__init__(
            name="docker-command",
            command=["docker", "--version"],
            hint="install Docker Desktop (https://docs.docker.com/get-docker/)",
        )

    def image_exists(self, tag: str) -> bool:
        """Return True if the Docker image *tag* exists locally."""
        r = subprocess.run(
            ["docker", "images", "-q", tag],
            capture_output=True,
            text=True,
        )
        return bool(r.returncode == 0 and r.stdout.strip())

    def container_exists(self, name: str) -> bool:
        """Return True if a container named *name* exists (running or stopped)."""
        return (
            subprocess.run(
                ["docker", "inspect", name],
                capture_output=True,
            ).returncode
            == 0
        )

    def is_running(self, name: str) -> tuple[bool, str]:
        """Return (running, message) by inspecting the named container."""
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip() == "true":
            return True, "ok"
        return False, "not started"

    def build_image(
        self,
        tag: str,
        context: str,
        dockerfile: str | None = None,
        no_cache: bool = False,
    ) -> None:
        """Build a Docker image, raising SystemExit on failure."""
        cmd = ["docker", "build"]
        if no_cache:
            cmd.append("--no-cache")
        if dockerfile:
            cmd.extend(["-f", dockerfile])
        cmd.extend(["-t", tag, context])
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    def run_detached(
        self,
        name: str,
        image: str,
        publish: list[str] | None = None,
        volumes: list[str] | None = None,
        rm: bool = True,
    ) -> int:
        """Run a container in detached mode; return the exit code."""
        cmd = ["docker", "run"]
        if rm:
            cmd.append("--rm")
        cmd.extend(["--detach", "--name", name])
        for p in (publish or []):
            cmd.extend(["--publish", p])
        for v in (volumes or []):
            cmd.extend(["-v", v])
        cmd.append(image)
        return subprocess.run(cmd).returncode

    def stop_container(self, name: str) -> None:
        """Stop a running container, ignoring errors."""
        subprocess.run(["docker", "stop", name], stderr=subprocess.DEVNULL)

    def remove_container(self, name: str) -> None:
        """Remove a container, ignoring errors."""
        subprocess.run(["docker", "rm", name], stderr=subprocess.DEVNULL)


DOCKER_COMMAND = comp_command_docker()
