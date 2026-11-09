"""git-access component: how to authenticate git to a repository URL."""

import os
import stat
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit


from .component_catalog_access_checker import CatalogAccessChecker
from .component_catalog_file import CatalogFile
from .component_with_config import ConfComp
from .configuration import Configuration
from .configuration_entry import ConfigurationEntry
from .dot_jejune import DotJejune


class CompGitAccess(ConfComp):
    """Turns a token file into a git-credential-store file.

    A token file holds one line `[username]:[password_or_token]`.  For each
    repository URL the generated credentials file holds one path-aware
    git-credential-store line
    `[protocol]://[username]:[token]@[host_or_domain]/[repository_path]`,
    to be used by git with `credential.useHttpPath=true`, so that every
    repository can have its own key.

    This component does not know where repositories live (ecosystem) nor which
    ones exist (catalog): callers hand it the repository URLs.
    """

    TOKEN_ENV_VAR = "GIT_ACCESS_TOKEN"
    TOKEN_FILE_ENV_VAR = "GIT_ACCESS_TOKEN_FILE"
    _GROUP_AND_OTHER_PERMISSIONS = stat.S_IRWXG | stat.S_IRWXO

    def __init__(self, git_command) -> None:
        super().__init__(
            name="git-access",
            dependencies=[git_command],
            hint=(
                "edit .jejune/env-secrets and set "
                f"{self.TOKEN_ENV_VAR} or {self.TOKEN_FILE_ENV_VAR}"
            ),
            configuration=Configuration(
                ConfigurationEntry(
                    self.TOKEN_ENV_VAR,
                    hint="edit .jejune/env-secrets",
                    source_file=".jejune/env-secrets",
                    max_severity="warn",
                    env_var_validator=self.validate_token,
                ),
                ConfigurationEntry(
                    self.TOKEN_FILE_ENV_VAR,
                    hint="edit .jejune/env-secrets",
                    source_file=".jejune/env-secrets",
                    max_severity="warn",
                    env_var_validator=self.validate_token_file,
                ),
                failure_hint="run `jejune git-access check-config`",
            ),
        )

    def check_catalog(self, catalog_path: Path) -> list[tuple[str, str, str]]:
        """Return (status, subject, message) rows, one per catalog entry."""
        return CatalogAccessChecker(self, catalog_path).run()

    def probe_catalog(self, catalog_path: Path) -> list[tuple[str, str, str]]:
        """Return (status, subject, message) rows, one per catalog entry that can
        be probed: the network is used, see CatalogAccessChecker.probe_remote."""
        return CatalogAccessChecker(self, catalog_path).probe_remote()

    def check(self) -> tuple[str, str]:
        """Each variable is optional on its own: only private repositories need one.

        When the current catalog exists, its entries must also have their access
        keys (own `token_file` or the environment): this is what makes the
        component available without any environment variable.
        """
        defined = [
            entry for entry in self.configuration.entries if entry.env_var in os.environ
        ]
        for entry in defined:
            status, message = entry.check()
            if status != "ok":
                return status, f"{entry.env_var}: {message}"
        catalog_path = CatalogFile.resolve_path()
        if catalog_path.is_file():
            for status, subject, message in self.check_catalog(catalog_path):
                if status == "error":
                    return status, f"{subject}: {message}"
            return "ok", ""
        if not defined:
            return (
                "warn",
                f"neither {self.TOKEN_ENV_VAR} nor {self.TOKEN_FILE_ENV_VAR} set",
            )
        return "ok", ""

    @staticmethod
    def parse_credentials(content: str, source: str) -> tuple[str, str]:
        """Return (username, token) out of a `[username]:[token]` line."""
        content = content.strip()
        username, separator, token = content.partition(":")
        if not separator or not username or not token or "\n" in content:
            raise ValueError(
                f"{source} must hold a single [username]:[password_or_token]"
            )
        return username, token

    @classmethod
    def read_token_file(cls, token_file: Path) -> tuple[str, str]:
        """Return (username, token) out of a `[username]:[token]` token file."""
        return cls.parse_credentials(token_file.read_text(), str(token_file))

    @classmethod
    def validate_token(cls, value: str) -> tuple[str, str]:
        try:
            cls.parse_credentials(value, cls.TOKEN_ENV_VAR)
        except ValueError as exc:
            return "error", str(exc)
        return "ok", ""

    @classmethod
    def validate_token_file(cls, value: str) -> tuple[str, str]:
        token_file = Path(value).expanduser()
        if not token_file.is_file():
            return "error", f"token file not found at {token_file.resolve()}"
        if token_file.stat().st_mode & cls._GROUP_AND_OTHER_PERMISSIONS:
            return (
                "error",
                f"token file {token_file} must only be accessible by you (chmod 600)",
            )
        try:
            cls.read_token_file(token_file)
        except ValueError as exc:
            return "error", str(exc)
        return "ok", ""

    @classmethod
    def resolve_credentials(
        cls, token_file: Path | str | None = None
    ) -> tuple[str, str] | None:
        """Return (username, token): the explicit token file wins, then
        GIT_ACCESS_TOKEN_FILE, then GIT_ACCESS_TOKEN; None when none is defined.

        Raises ValueError when the selected source is invalid.
        """
        file_value = token_file or os.environ.get(cls.TOKEN_FILE_ENV_VAR)
        if file_value:
            status, message = cls.validate_token_file(str(file_value))
            if status != "ok":
                raise ValueError(message)
            return cls.read_token_file(Path(file_value).expanduser())
        token_value = os.environ.get(cls.TOKEN_ENV_VAR)
        if token_value:
            return cls.parse_credentials(token_value, cls.TOKEN_ENV_VAR)
        return None

    @staticmethod
    def credentials_line(repository_url: str, username: str, token: str) -> str:
        """Return the git-credential-store line matching *repository_url*."""
        parts = urlsplit(repository_url)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return (
            f"{parts.scheme}://{quote(username, safe='')}:{quote(token, safe='')}"
            f"@{host}{parts.path}"
        )

    @contextmanager
    def credentials_file(
        self, repository_urls: list[str], token_file: Path | str | None = None
    ) -> Generator[Path | None]:
        """Yield a temporary git-credential-store file (mode 0600), removed on exit.

        Yields None when there is no token (file) or no repository URL, i.e. when
        no authentication is needed (public repositories).
        """
        with self.credentials_file_for_entries(
            [(repository_url, None) for repository_url in repository_urls],
            token_file,
        ) as credentials:
            yield credentials

    @contextmanager
    def credentials_file_for_entries(
        self,
        repositories: list[tuple[str, Path | str | None]],
        default_token_file: Path | str | None = None,
    ) -> Generator[Path | None]:
        """Same as credentials_file, with a token file of its own per repository.

        *repositories* holds (repository_url, token_file) pairs.  A repository
        without token file uses *default_token_file*, else the environment.
        Repositories having no token at all are left out of the file.
        """
        lines = []
        for repository_url, repository_token_file in repositories:
            resolved = self.resolve_credentials(
                repository_token_file or default_token_file
            )
            if resolved is not None:
                lines.append(self.credentials_line(repository_url, *resolved))
        if not lines:
            yield None
            return
        # .jejune/ is already gitignored by `configuration init`: no tmp_dir() here,
        # it would also append .jejune/tmp/ to the .gitignore of the document.
        scratch_dir = DotJejune() / "tmp"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=scratch_dir, prefix="git-credentials-")
        credentials = Path(name)
        try:
            with os.fdopen(descriptor, "w") as handle:
                handle.write("\n".join(lines) + "\n")
            yield credentials
        finally:
            credentials.unlink(missing_ok=True)

    def run_git(
        self,
        arguments: list[str],
        repository_url: str | None = None,
        token_file: Path | str | None = None,
        **run_options,
    ) -> subprocess.CompletedProcess:
        """Run `git <arguments>`, authenticated for *repository_url* when a token
        is defined.  The token never appears in argv, in a URL nor in .git/config.

        *run_options* are handed to subprocess.run.
        """
        with self.credentials_file(
            [repository_url] if repository_url else [], token_file
        ) as credentials:
            authentication = (
                []
                if credentials is None
                else [
                    "-c",
                    "credential.useHttpPath=true",
                    "-c",
                    "credential.helper=",
                    "-c",
                    f"credential.helper=store --file={credentials}",
                ]
            )
            return subprocess.run(["git", *authentication, *arguments], **run_options)

    def ls_remote(
        self,
        repository_url: str,
        token_file: Path | str | None = None,
        *references: str,
        **run_options,
    ) -> subprocess.CompletedProcess:
        """Run `git ls-remote <repository_url> <references>`, authenticated as
        run_git does.  Output is captured as text; *run_options* go to subprocess.run.
        """
        return self.run_git(
            ["ls-remote", repository_url, *references],
            repository_url,
            token_file,
            capture_output=True,
            text=True,
            **run_options,
        )

    @staticmethod
    def ls_remote_anonymous(
        arguments: list[str], timeout: int
    ) -> subprocess.CompletedProcess:
        """Run `git ls-remote <arguments>` without any credentials (text output)."""
        return subprocess.run(
            ["git", "ls-remote", *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    @staticmethod
    def origin_url(repo_path: Path) -> str | None:
        """Return the URL of the `origin` remote of the clone *repo_path*."""
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None if result.returncode == 0 else None

    @staticmethod
    def head_sha(repo_path: Path) -> str:
        """Return the commit SHA of HEAD in *repo_path*; CalledProcessError on failure."""
        return subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
