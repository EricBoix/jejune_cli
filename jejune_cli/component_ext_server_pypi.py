"""PyPI server component."""
import urllib.error
import urllib.request

from .component_ext_server import ext_server
from .component_ext_network import comp_network

_PYPI_API_URL = "https://pypi.org/pypi/pip/json"


class comp_server_pypi(ext_server):
    def __init__(self, network: comp_network) -> None:
        super().__init__(
            name="pypi-server",
            api_url=_PYPI_API_URL,
            dependencies=[network],
        )

    def check(self) -> tuple[str, str]:
        try:
            urllib.request.urlopen(self.api_url, timeout=5)
            return "ok", ""
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return "ok", ""
            return "error", f"PyPI returned HTTP {exc.code}"
        except Exception as exc:
            return "error", f"PyPI not reachable: {exc}"
