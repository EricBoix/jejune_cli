"""Network connectivity component."""
import platform
import subprocess

from .component_ext import ext_comp
from .component_registry import REGISTRY


class comp_network(ext_comp):
    def __init__(self) -> None:
        super().__init__(
            name="network",
            hint="check internet connectivity (GitHub must be reachable)",
        )
        self.remote_server = "www.google.com"
        self.visible = lambda: REGISTRY.get("ecosystem").ecosystem_needs_remote()
        type(self).registry.add(self)

    def check(self) -> tuple[str, str]:
        if not REGISTRY.get("ecosystem").ecosystem_needs_remote():
            return "ok", ""
        ok = _ping(self.remote_server)
        return ("ok", "") if ok else ("error", "GitHub not reachable")


def _ping(host: str) -> bool:
    timeout_flag = "-t" if platform.system() == "Darwin" else "-W"
    try:
        subprocess.run(
            ["ping", "-c", "1", timeout_flag, "3", host],
            capture_output=True, check=True,
        )
        return True
    except Exception:
        return False


comp_network()
