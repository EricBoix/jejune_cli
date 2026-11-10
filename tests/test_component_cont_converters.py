from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from jejune_cli import component_cont_converters
from jejune_cli.component_cont_converters import CompConverters

PRIVATE_URL = "https://example.org/team/jejune_doc_Private.git"


@pytest.fixture
def converters(tmp_path, monkeypatch):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(f"RUN git clone {PRIVATE_URL}\n")
    repo_dir = tmp_path / "jejune_doc_Private"
    selection = SimpleNamespace(documents=[{"name": "Private"}], directories=None)
    collection = SimpleNamespace(
        select=lambda: selection,
        iter_documents=lambda documents, directories: [("Private", "", repo_dir)],
    )
    requested = []

    @contextmanager
    def credentials_file(repository_urls, token_file=None):
        requested.append((repository_urls, token_file))
        yield tmp_path / "credentials"

    instance = CompConverters.__new__(CompConverters)
    instance._catalog_comp = SimpleNamespace(collection=collection)
    instance._context = SimpleNamespace(
        git_access=SimpleNamespace(credentials_file=credentials_file)
    )
    instance.has_converter = lambda directory: (True, dockerfile, tmp_path)
    monkeypatch.setattr(
        component_cont_converters.CatalogFile,
        "token_files",
        lambda self: {"Private": "private.access_keys"},
    )
    monkeypatch.setattr(
        component_cont_converters.CatalogFile, "__init__", lambda self, path: None
    )
    monkeypatch.setattr(
        component_cont_converters.CatalogFile, "resolve_path", lambda: tmp_path
    )
    instance.requested = requested
    instance.credentials = tmp_path / "credentials"
    return instance


def test_build_hands_private_credentials_over_as_buildkit_secret(
    converters, monkeypatch
):
    commands = []
    monkeypatch.setattr(
        component_cont_converters.subprocess,
        "run",
        lambda command, check: commands.append(command),
    )
    converters.build()
    assert converters.requested == [([PRIVATE_URL], "private.access_keys")]
    assert (
        "--secret",
        f"id=git_credentials,src={converters.credentials}",
    ) in zip(commands[0], commands[0][1:])
