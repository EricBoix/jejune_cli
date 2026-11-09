"""Reading a catalog.yaml: the one place that knows its `documents` layout."""

import os
from pathlib import Path

import yaml

from .component_catalog_document import CatalogDocument


class CatalogFile:
    """A catalog.yaml: `documents`, a list of mappings."""

    PATH_ENV_VAR = "JEJUNE_CATALOG"
    DEFAULT_FILE_NAME = "catalog.yaml"

    @classmethod
    def resolve_path(cls, catalog_option: Path | str | None = None) -> Path:
        """The catalog to use: explicit, else JEJUNE_CATALOG, else ./catalog.yaml."""
        return Path(
            catalog_option
            or os.environ.get(cls.PATH_ENV_VAR)
            or Path.cwd() / cls.DEFAULT_FILE_NAME
        )

    def __init__(self, path: Path) -> None:
        self._path = path

    def raw_documents(self) -> list:
        """The items of `documents`, as written; ValueError when unreadable."""
        try:
            data = yaml.safe_load(self._path.read_text()) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML: {exc}") from exc
        documents = data.get("documents") if isinstance(data, dict) else None
        if not isinstance(documents, list):
            raise ValueError("no `documents` list")
        return documents

    def documents(self) -> list[CatalogDocument]:
        """The well-formed documents (with a `name` and a `url`)."""
        return [
            document
            for document in map(CatalogDocument.from_mapping, self.raw_documents())
            if document is not None
        ]

    def names(self) -> list[str]:
        """Names of the entries having one, whether or not they have a `url`."""
        return [
            item["name"]
            for item in self.raw_documents()
            if isinstance(item, dict) and item.get("name")
        ]

    def private_documents(self) -> list[CatalogDocument]:
        return [document for document in self.documents() if document.is_private]

    def token_files(self) -> dict[str, str]:
        """Token file of every private document having one, by name.

        An unreadable catalog yields no token file at all.
        """
        try:
            private_documents = self.private_documents()
        except ValueError:
            return {}
        return {
            document.name: document.token_file
            for document in private_documents
            if document.token_file
        }
