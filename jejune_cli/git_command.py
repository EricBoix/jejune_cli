"""Git CLI presence check for the `git-command` doctor component."""

import subprocess


def is_git_command_available() -> bool:
    """Return True if git is available on PATH."""
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False
