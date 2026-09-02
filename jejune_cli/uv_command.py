"""uv CLI presence check for the `uv-command` doctor component."""

import subprocess


def is_uv_command_available() -> bool:
    """Return True if uv is available on PATH."""
    try:
        subprocess.run(["uv", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False
