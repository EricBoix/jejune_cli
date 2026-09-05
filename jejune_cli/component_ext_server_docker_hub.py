"""Docker Hub server component."""
import urllib.error
import urllib.request

from .component_ext_server import ext_server

_DOCKERHUB_API_URL = "https://hub.docker.com/v2/"


class comp_server_docker_hub(ext_server):
    def __init__(self) -> None:
        super().__init__(
            name="docker-hub-server",
            api_url=_DOCKERHUB_API_URL,
            dependencies=[type(self).registry.get("network")],
        )
        type(self).registry.add(self)

    def check(self) -> tuple[str, str]:
        try:
            urllib.request.urlopen(self.api_url, timeout=5)
            return "ok", ""
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return "ok", ""
            return "error", f"Docker Hub returned HTTP {exc.code}"
        except Exception as exc:
            return "error", f"Docker Hub not reachable: {exc}"


comp_server_docker_hub()
