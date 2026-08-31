"""Git availability check for the `git_repos` doctor component."""

import subprocess


def check_git() -> bool:
    """Return True if git is available on PATH."""
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False
