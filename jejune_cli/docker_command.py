"""Docker CLI presence check for the `docker` doctor component."""

import subprocess


def is_docker_command_available() -> bool:
    """Return True if docker is available on PATH."""
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        return True
    except Exception:
        return False
