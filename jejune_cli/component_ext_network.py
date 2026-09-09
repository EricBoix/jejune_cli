"""Network connectivity component."""
import socket

from .component_ext import ext_comp
from .component_registry import ComponentRegistry


class comp_network(ext_comp):
    def __init__(self) -> None:
        self.remote_server = "www.google.com"
        super().__init__(
            name="network",
            hint=f"check internet connectivity (e.g. ping {self.remote_server})",
        )

    def check(self) -> tuple[str, str]:
        if not ComponentRegistry().get("ecosystem").ecosystem_needs_remote():
            return "ok", ""
        ok = _tcp_reachable(self.remote_server)
        return ("ok", "") if ok else ("error", f"{self.remote_server} not reachable")


def _tcp_reachable(host: str, port: int = 443, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


