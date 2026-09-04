"""PyPI server component."""
import urllib.error
import urllib.request

from .component_ext_server import ext_server
from .component_registry import REGISTRY

_PYPI_API_URL = "https://pypi.org/pypi/pip/json"


class comp_server_pypi(ext_server):
    def __init__(self) -> None:
        super().__init__(
            name="pypi-server",
            api_url=_PYPI_API_URL,
            dependencies=[REGISTRY.get("network")],
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


REGISTRY.add(comp_server_pypi())
