"""git-server component."""
import subprocess

from ._git_server_config import REPO_ROOT_DIR as _REPO_ROOT_DIR
from .component_ext_server import ext_server


class comp_server_git(ext_server):
    def __init__(self) -> None:
        super().__init__(
            name="git-server",
            api_url="",
            dependencies=[type(self).registry.get("network"), type(self).registry.get("git-command")],
        )
        type(self).registry.add(self)

    def repo_root_dir(self) -> str:
        return _REPO_ROOT_DIR

    def remote_repo_path(self, name: str) -> str:
        """Return the bare remote URL for a repo (no .git suffix)."""
        return f"{_REPO_ROOT_DIR}/{name}"

    def remote_git_url(self, name: str, fragment: str | None = None) -> str:
        """Return the git URL for a repo, with optional #fragment."""
        url = f"{_REPO_ROOT_DIR}/{name}.git"
        return f"{url}#{fragment}" if fragment else url

    def remote_pip_url(self, name: str, subpath: str) -> str:
        """Return the pip-install git URL for a repo subdirectory."""
        return f"git+{_REPO_ROOT_DIR}/{name}.git#subdirectory={subpath}"

    def check(self, timeout: int = 5) -> tuple[str, str]:
        try:
            r = subprocess.run(
                ["git", "ls-remote", _REPO_ROOT_DIR],
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


comp_server_git()
