"""Docker Hub availability check for the `docker-hub-server` doctor component."""

import urllib.error
import urllib.request

_DOCKERHUB_API_URL = "https://hub.docker.com/v2/"


def check_docker_hub_server(timeout: int = 5) -> tuple[bool, str]:
    """Return (True, "") if Docker Hub API is reachable, (False, reason) otherwise."""
    try:
        urllib.request.urlopen(_DOCKERHUB_API_URL, timeout=timeout)
        return True, ""
    except urllib.error.HTTPError as exc:
        # Any HTTP response (including 401 Unauthorized) means the service is reachable.
        if exc.code < 500:
            return True, ""
        return False, f"Docker Hub returned HTTP {exc.code}"
    except Exception as exc:
        return False, f"Docker Hub not reachable: {exc}"


def is_docker_hub_server_available() -> bool:
    return check_docker_hub_server()[0]
