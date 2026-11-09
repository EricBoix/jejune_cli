"""git-server component."""

import socket
import subprocess
from typing import Protocol
from urllib.parse import urlsplit

from ._git_server_config import REPO_ROOT_DIR as _REPO_ROOT_DIR
from .component_git_access import CompGitAccess
from .component_ext_server import ExtServer
from .component_ext_network import CompNetwork
from .component_ext_command_git import CompCommandGit


class RepositoryUrlSource(Protocol):
    """A component knowing repository URLs in use (catalog entries, `git clone`
    URLs of a Dockerfile)."""

    def repository_urls(self) -> list[str]: ...


class CompServerGit(ExtServer):
    """Asserts that every git host_or_domain in use is reachable.

    Besides the default ecosystem host, the hosts are those of the repository
    URLs of the registered URL sources (see add_url_source).  They are not
    dependencies (not in the topology) because the catalog depends on the
    ecosystem which depends on this component.
    """

    def __init__(self, network: CompNetwork, git_command: CompCommandGit) -> None:
        super().__init__(
            name="git-server",
            api_url="",
            dependencies=[network, git_command],
        )
        self._url_sources: list[RepositoryUrlSource] = []

    def add_url_source(self, source: RepositoryUrlSource) -> None:
        """Have the hosts of the repository URLs of *source* asserted reachable."""
        self._url_sources.append(source)

    def repo_root_dir(self) -> str:
        return _REPO_ROOT_DIR

    def remote_repo_path(self, name: str) -> str:
        """Return the bare remote URL for a repo (no .git suffix)."""
        return f"{_REPO_ROOT_DIR}/{name}"

    def remote_git_url(self, name: str, fragment: str | None = None) -> str:
        """Return the git URL for a repo, with optional #fragment."""
        url = f"{self.remote_repo_path(name)}.git"
        return f"{url}#{fragment}" if fragment else url

    def remote_pip_url(self, name: str) -> str:
        """Return the pip-install git URL for a repo."""
        return f"git+{self.remote_git_url(name)}"

    def hosts(self) -> list[tuple[str, int]]:
        """Return the distinct (host_or_domain, port) beyond the default host."""
        default = self._host_and_port(_REPO_ROOT_DIR)
        hosts: list[tuple[str, int]] = []
        for source in self._url_sources:
            for repository_url in source.repository_urls():
                host = self._host_and_port(repository_url)
                if host is not None and host != default and host not in hosts:
                    hosts.append(host)
        return hosts

    @staticmethod
    def _host_and_port(url: str) -> tuple[str, int] | None:
        parts = urlsplit(url)
        if not parts.hostname:
            return None
        return parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)

    def check(self, timeout: int = 5) -> tuple[str, str]:
        status, message = self.check_default_host(timeout)
        unreachable = []
        for host, port in self.hosts():
            try:
                socket.create_connection((host, port), timeout=timeout).close()
            except OSError:
                unreachable.append(host)
        if unreachable:
            hosts = ", ".join(unreachable)
            return "error", "; ".join(filter(None, [message, f"unreachable: {hosts}"]))
        return status, message

    def check_default_host(self, timeout: int = 5) -> tuple[str, str]:
        try:
            r = CompGitAccess.ls_remote_anonymous([_REPO_ROOT_DIR], timeout)
            if r.returncode == 0:
                return "ok", ""
            stderr = r.stderr.lower()
            if "not found" in stderr:
                return "ok", ""
            return "error", "git server not reachable"
        except subprocess.TimeoutExpired:
            return "error", "git server timed out"
        except Exception as exc:
            return "error", str(exc)
