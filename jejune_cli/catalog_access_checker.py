"""Cross-check of the entries of a catalog.yaml with their access-key files."""

import subprocess
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import yaml


class TokenSource(Protocol):
    """What the checker needs from the git-access component.

    A protocol rather than CompGitAccess itself: the component imports this
    module, so importing the component here would be circular.
    """

    TOKEN_ENV_VAR: str
    TOKEN_FILE_ENV_VAR: str

    def validate_token_file(self, value: str) -> tuple[str, str]: ...

    def resolve_credentials(
        self, token_file: Path | str | None = None
    ) -> tuple[str, str] | None: ...

    def ls_remote(
        self,
        repository_url: str,
        token_file: Path | str | None = None,
        *references: str,
        **run_options,
    ) -> subprocess.CompletedProcess: ...


class CatalogAccessChecker:
    """Cross-checks the entries of a catalog.yaml with their access-key files."""

    _PROBE_TIMEOUT_SECONDS = 30

    def __init__(self, comp: TokenSource, catalog_path: Path) -> None:
        self._comp = comp
        self._catalog_path = catalog_path
        self._key_lines: dict[tuple[int, str], int] = {}

    def _load_documents(self) -> tuple[list, list[tuple[str, str, str]]]:
        """Return (documents, error_rows): error_rows is not empty when the
        catalog cannot be read, in which case documents is empty."""
        if not self._catalog_path.is_file():
            return [], [("error", str(self._catalog_path), "catalog file not found")]
        text = self._catalog_path.read_text()
        try:
            data = yaml.safe_load(text) or {}
            self._index_key_lines(yaml.compose(text))
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f"{self._catalog_path}:{mark.line + 1}" if mark else ""
            return [], [
                ("error", where or str(self._catalog_path), f"invalid YAML: {exc}")
            ]
        documents = data.get("documents", []) if isinstance(data, dict) else None
        if not isinstance(documents, list):
            return [], [("error", str(self._catalog_path), "no `documents` list")]
        return documents, []

    def run(self) -> list[tuple[str, str, str]]:
        """Return (status, subject, message) rows; status is ok, warn or error.

        Local checks only: the files are looked at, the network is never used.
        """
        documents, error_rows = self._load_documents()
        if error_rows:
            return error_rows
        rows = []
        for index, document in enumerate(documents, 1):
            rows.extend(self._check_document(index, document))
        if not rows:
            rows.append(("ok", str(self._catalog_path), "no document entries"))
        return rows

    def probe_remote(self) -> list[tuple[str, str, str]]:
        """Return (status, subject, message) rows, one per probed entry.

        Each entry is probed with `git ls-remote` using its own credentials, which
        tells whether the url exists and whether the key gives read access to it.
        An entry that run() already reports as unusable (no url, invalid or
        missing key) is not probed.  GitHub answers "not found" both to a wrong
        url and to a private repository the key cannot see: hence the message.
        """
        documents, _ = self._load_documents()
        rows = []
        for index, document in enumerate(documents, 1):
            if not isinstance(document, dict) or "url" not in document:
                continue
            url = document["url"]
            name = document.get("name", url)
            public = document.get("public", True)
            token_file = None if public else document.get("token_file")
            try:
                credentials = self._comp.resolve_credentials(token_file)
            except ValueError:
                continue
            if not public and credentials is None:
                continue
            rows.append(self._probe_document(index, name, url, token_file))
        return rows

    def _probe_document(
        self, index: int, name: str, url: str, token_file: str | None
    ) -> tuple[str, str, str]:
        location = self._location(index, "url")
        try:
            completed = self._comp.ls_remote(
                url, token_file, "HEAD", timeout=self._PROBE_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired:
            return (
                "error",
                location,
                f"`{name}` not reachable: no answer from {url} "
                f"after {self._PROBE_TIMEOUT_SECONDS}s",
            )
        except OSError as exc:
            return ("error", location, f"`{name}` cannot be probed: {exc}")
        if completed.returncode == 0:
            return ("ok", location, f"`{name}` reachable ({url})")
        return (
            "error",
            location,
            f"`{name}` not reachable: wrong url or no access ({url})",
        )

    def _index_key_lines(self, root) -> None:
        """Record the 1-based line of each key of each entry of `documents`."""
        if not isinstance(root, yaml.MappingNode):
            return
        for key_node, value_node in root.value:
            if key_node.value != "documents" or not isinstance(
                value_node, yaml.SequenceNode
            ):
                continue
            for index, entry in enumerate(value_node.value, 1):
                if not isinstance(entry, yaml.MappingNode):
                    continue
                self._key_lines[(index, "")] = entry.start_mark.line + 1
                for entry_key, _ in entry.value:
                    self._key_lines[(index, entry_key.value)] = (
                        entry_key.start_mark.line + 1
                    )

    def _location(self, index: int, key: str = "") -> str:
        line = self._key_lines.get((index, key)) or self._key_lines.get((index, ""))
        return f"{self._catalog_path}:{line}" if line else str(self._catalog_path)

    def _check_document(self, index: int, document) -> list[tuple[str, str, str]]:
        if not isinstance(document, dict) or "url" not in document:
            return [("error", self._location(index), "entry without a `url`")]
        url = document["url"]
        name = document.get("name", url)
        public = document.get("public", True)
        token_file = document.get("token_file")
        url_problem = self._url_problem(url)
        if url_problem:
            return [
                (
                    "error",
                    self._location(index, "url"),
                    f"entry `{name}`: `url: {url}` {url_problem}",
                )
            ]
        if public:
            if token_file:
                return [
                    (
                        "warn",
                        self._location(index, "token_file"),
                        f"entry `{name}` is public but has a `token_file`, which is unused",
                    )
                ]
            return [("ok", self._location(index), f"`{name}` is public")]
        if token_file:
            return [self._check_token_file(index, name, str(token_file))]
        try:
            resolved = self._comp.resolve_credentials()
        except ValueError as exc:
            return [("error", self._location(index, "public"), f"`{name}`: {exc}")]
        if resolved is None:
            return [
                (
                    "error",
                    self._location(index, "public"),
                    f"entry `{name}` is private (`public: false`) but has no "
                    "`token_file` and neither "
                    f"{self._comp.TOKEN_ENV_VAR} nor "
                    f"{self._comp.TOKEN_FILE_ENV_VAR} is set",
                )
            ]
        return [
            (
                "ok",
                self._location(index),
                f"`{name}` is private, default credentials from the environment",
            )
        ]

    @staticmethod
    def _url_problem(url) -> str:
        """Return why *url* cannot designate a repository, "" when it can."""
        if not isinstance(url, str):
            return "is not a string"
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and (
            len([part for part in parsed.path.split("/") if part]) < 2
        ):
            return "has no <owner>/<repository> path"
        return ""

    def _check_token_file(
        self, index: int, name: str, token_file: str
    ) -> tuple[str, str, str]:
        location = self._location(index, "token_file")
        resolved = Path(token_file).expanduser()
        if not resolved.exists():
            return (
                "error",
                location,
                f"entry `{name}`: `token_file: {token_file}` does not exist "
                f"(looked for {resolved.resolve()})",
            )
        status, message = self._comp.validate_token_file(token_file)
        if status != "ok":
            return (
                status,
                location,
                f"entry `{name}`: `token_file: {token_file}`: {message}",
            )
        return (
            "ok",
            location,
            f"`{name}` is private, token file {token_file} is well-formed",
        )
