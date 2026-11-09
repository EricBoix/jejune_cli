from pathlib import Path
from types import SimpleNamespace

import pytest

from jejune_cli.component_catalog_document import CatalogDocument
from jejune_cli.component_catalog_file import CatalogFile


def write_catalog(tmp_path, content: str):
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(content)
    return catalog_path


def test_documents_skip_entries_without_name_or_url(tmp_path):
    catalog_path = write_catalog(
        tmp_path,
        "documents:\n"
        "  - {name: a, url: https://h/a.git}\n"
        "  - {name: b}\n"
        "  - not-a-mapping\n",
    )
    catalog = CatalogFile(catalog_path)
    assert catalog.documents() == [CatalogDocument("a", "https://h/a.git")]
    assert catalog.names() == ["a", "b"]


def test_unreadable_catalog_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="invalid YAML"):
        CatalogFile(write_catalog(tmp_path, "documents: [")).raw_documents()
    with pytest.raises(ValueError, match="no `documents` list"):
        CatalogFile(write_catalog(tmp_path, "other: 1\n")).raw_documents()


def test_token_files_only_of_private_documents(tmp_path):
    catalog_path = write_catalog(
        tmp_path,
        "documents:\n"
        "  - {name: a, url: https://h/a.git, token_file: ~/ignored}\n"
        "  - {name: b, url: https://h/b.git, public: false, token_file: ~/key}\n"
        "  - {name: c, url: https://h/c.git, public: false}\n",
    )
    assert CatalogFile(catalog_path).token_files() == {"b": "~/key"}


def test_private_document_requires_credentials():
    git_access = SimpleNamespace(
        TOKEN_ENV_VAR="TOKEN",
        TOKEN_FILE_ENV_VAR="TOKEN_FILE",
        resolve_credentials=lambda token_file=None: None,
    )
    assert CatalogDocument("a", "https://h/a.git").resolve_credentials(git_access) is None
    private = CatalogDocument("b", "https://h/b.git", public=False)
    with pytest.raises(ValueError, match="private"):
        private.resolve_credentials(git_access)


def test_resolve_path_prefers_option_then_environment_then_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CatalogFile.PATH_ENV_VAR, raising=False)
    assert CatalogFile.resolve_path() == tmp_path / "catalog.yaml"
    monkeypatch.setenv(CatalogFile.PATH_ENV_VAR, "from-env.yaml")
    assert CatalogFile.resolve_path() == Path("from-env.yaml")
    assert CatalogFile.resolve_path(tmp_path / "option.yaml") == tmp_path / "option.yaml"
