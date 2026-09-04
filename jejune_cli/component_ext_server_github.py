"""github-server component."""
import subprocess

from ._git_server_config import REPO_ROOT_DIR
from .component_ext_server import ext_server
from .component_registry import REGISTRY


class comp_server_github(ext_server):
    def __init__(self) -> None:
        super().__init__(
            name="github-server",
            api_url="",
            dependencies=[REGISTRY.get("network"), REGISTRY.get("git-command")],
        )

    def check(self, timeout: int = 5) -> tuple[str, str]:
        try:
            r = subprocess.run(
                ["git", "ls-remote", REPO_ROOT_DIR],
                capture_output=True, timeout=timeout,
            )
            if r.returncode == 0:
                return "ok", ""
            stderr = r.stderr.decode(errors="replace").lower()
            if "not found" in stderr:
                return "ok", ""
            return "error", "git server not reachable"
        except subprocess.TimeoutExpired:
            return "error", "git server timed out"
        except Exception as exc:
            return "error", str(exc)


REGISTRY.add(comp_server_github())
