"""Network availability check for the `network` doctor component."""

import urllib.request

from ._ecosystem import REPO_ROOT_DIR


def check_network(timeout: int = 5) -> bool:
    """Return True if REPO_ROOT_DIR is reachable over HTTP."""
    try:
        urllib.request.urlopen(REPO_ROOT_DIR, timeout=timeout)
        return True
    except Exception:
        return False
