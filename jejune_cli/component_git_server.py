"""git-server doctor component."""

import subprocess

REPO_ROOT_DIR = "https://github.com/EricBoix"


def remote_repo_path(name: str) -> str:
    """Return the bare remote URL for a repo (no .git suffix)."""
    return f"{REPO_ROOT_DIR}/{name}"


def remote_git_url(name: str, fragment: str | None = None) -> str:
    """Return the git URL for a repo, with optional #fragment."""
    url = f"{REPO_ROOT_DIR}/{name}.git"
    return f"{url}#{fragment}" if fragment else url


def remote_pip_url(name: str, subpath: str) -> str:
    """Return the pip-install git URL for a repo subdirectory."""
    return f"git+{REPO_ROOT_DIR}/{name}.git#subdirectory={subpath}"


def is_git_server_available(timeout: int = 5) -> bool:
    """Return True if REPO_ROOT_DIR is reachable via git.

    A 'repository not found' response means the server answered — enough to
    confirm reachability.
    """
    try:
        r = subprocess.run(
            ["git", "ls-remote", REPO_ROOT_DIR],
            capture_output=True, timeout=timeout,
        )
        if r.returncode == 0:
            return True
        return "not found" in r.stderr.decode(errors="replace").lower()
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False
