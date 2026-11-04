"""Network connectivity component."""

import socket
import subprocess

from .component_ext import ExtComp


class CompNetwork(ExtComp):
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

    def port_in_time_wait(self, port: int) -> bool:
        """Return True if *port* only lingers in TIME_WAIT (e.g. a container just stopped)."""
        try:
            netstat = subprocess.run(
                ["netstat", "-an"], capture_output=True, text=True, timeout=5
            )
        except (OSError, subprocess.SubprocessError):
            return False
        port_suffixes = (f".{port}", f":{port}")
        port_states = [
            columns[-1]
            for columns in (line.split() for line in netstat.stdout.splitlines())
            if columns
            and any(column.endswith(port_suffixes) for column in columns[3:5])
        ]
        return bool(port_states) and all(state == "TIME_WAIT" for state in port_states)


def _tcp_reachable(host: str, port: int = 443, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
