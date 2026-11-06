"""git-access component: how to authenticate git to a repository URL."""

import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit

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
            ),
        )

    def check(self) -> tuple[str, str]:
        """Each variable is optional on its own: only private repositories need one."""
        defined = [
            entry for entry in self.configuration.entries if entry.env_var in os.environ
        ]
        if not defined:
            return (
                "warn",
                f"neither {self.TOKEN_ENV_VAR} nor {self.TOKEN_FILE_ENV_VAR} set",
            )
        for entry in defined:
            status, message = entry.check()
            if status != "ok":
                return status, f"{entry.env_var}: {message}"
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
    ) -> Iterator[Path | None]:
        """Yield a temporary git-credential-store file (mode 0600), removed on exit.

        Yields None when there is no token (file) or no repository URL, i.e. when
        no authentication is needed (public repositories).
        """
        resolved = self.resolve_credentials(token_file)
        if resolved is None or not repository_urls:
            yield None
            return
        username, token = resolved
        lines = [
            self.credentials_line(repository_url, username, token)
            for repository_url in repository_urls
        ]
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
