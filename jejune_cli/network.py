"""Network availability check for the `network` doctor component."""

import urllib.request

_WELL_KNOWN_URL = "https://www.google.com"


def is_network_available(timeout: int = 5) -> bool:
    """Return True if the internet is reachable."""
    try:
        urllib.request.urlopen(_WELL_KNOWN_URL, timeout=timeout)
        return True
    except Exception:
        return False
