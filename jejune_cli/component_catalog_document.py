"""One document entry of a catalog.yaml."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class CredentialsResolver(Protocol):
    """What a document needs from the git-access component.

    A protocol rather than CompGitAccess itself: the component imports modules
    that read catalogs, so importing the component here would be circular.
    """

    TOKEN_ENV_VAR: str
    TOKEN_FILE_ENV_VAR: str

    def resolve_credentials(
        self, token_file: Path | str | None = None
    ) -> tuple[str, str] | None: ...


@dataclass(frozen=True)
class CatalogDocument:
    """One document entry of a catalog.yaml."""

    name: str
    url: str
    public: bool = True
    token_file: str | None = None

    @classmethod
    def from_mapping(cls, mapping: object) -> "CatalogDocument | None":
        """The document described by *mapping*; None without a `name` or a `url`."""
        if not isinstance(mapping, dict) or not (
            mapping.get("name") and mapping.get("url")
        ):
            return None
        return cls(
            name=mapping["name"],
            url=mapping["url"],
            public=mapping.get("public", True),
            token_file=mapping.get("token_file"),
        )

    @property
    def is_private(self) -> bool:
        return not self.public

    @property
    def effective_token_file(self) -> str | None:
        """The token file of a public document is unused (git-access warns of it)."""
        return self.token_file if self.is_private else None

    def resolve_credentials(
        self, git_access: CredentialsResolver
    ) -> tuple[str, str] | None:
        """Return (username, token) to access the document, None when public.

        Raises ValueError when the selected source is invalid, or when the
        document is private and no source is defined.
        """
        credentials = git_access.resolve_credentials(self.effective_token_file)
        if self.is_private and credentials is None:
            raise ValueError(
                "private (`public: false`) but no `token_file` and "
                f"neither {git_access.TOKEN_ENV_VAR} nor "
                f"{git_access.TOKEN_FILE_ENV_VAR} is set"
            )
        return credentials
