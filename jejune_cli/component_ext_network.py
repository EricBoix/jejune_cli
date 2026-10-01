"""Network connectivity component."""

import socket

from .component_ext import ExtComp


class comp_network(ExtComp):
    def __init__(self) -> None:
        self.remote_server = "www.google.com"
        super().__init__(
            name="network",
            hint=f"check internet connectivity (e.g. ping {self.remote_server})",
        )

    def check(self) -> tuple[str, str]:
        ecosystem = self.runtime_dependencies.get("ecosystem")
        if ecosystem is None or not ecosystem.ecosystem_needs_remote():
            return "ok", ""
        ok = _tcp_reachable(self.remote_server)
        return ("ok", "") if ok else ("error", f"{self.remote_server} not reachable")

    def port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return True
            except OSError:
                return False


def _tcp_reachable(host: str, port: int = 443, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
