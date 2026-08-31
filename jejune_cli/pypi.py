"""PyPI availability check for the `pypi` doctor component."""

import urllib.error
import urllib.request

_PYPI_API_URL = "https://pypi.org/pypi/pip/json"


def check_pypi(timeout: int = 5) -> tuple[bool, str]:
    """Return (True, "") if PyPI is reachable, (False, reason) otherwise."""
    try:
        urllib.request.urlopen(_PYPI_API_URL, timeout=timeout)
        return True, ""
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            return True, ""
        return False, f"PyPI returned HTTP {exc.code}"
    except Exception as exc:
        return False, f"PyPI not reachable: {exc}"
