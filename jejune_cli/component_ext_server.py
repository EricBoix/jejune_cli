"""Base class for server-based external components."""
import urllib.error
import urllib.request

from .configuration import configuration as _configuration
from .component_ext import ext_comp


class ext_server(ext_comp):
    """External server reachable via HTTP. Subclasses override check() for non-HTTP."""

    def __init__(
        self,
        name: str,
        api_url: str,
        dependencies: list[str] | None = None,
        hint: str | None = None,
        configuration: _configuration | None = None,
    ) -> None:
        super().__init__(name=name, dependencies=dependencies, hint=hint)
        self.api_url = api_url
        self.configuration = configuration if configuration is not None else _configuration()

    def check(self) -> tuple[str, str]:
        try:
            urllib.request.urlopen(self.api_url, timeout=5)
            return "ok", ""
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return "ok", ""
            return "error", f"{self.name} returned HTTP {exc.code}"
        except Exception as exc:
            return "error", f"{self.name} not reachable: {exc}"
