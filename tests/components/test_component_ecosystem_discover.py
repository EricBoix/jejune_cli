from types import SimpleNamespace

from jejune_cli.components.component_ecosystem import (
    CompEcosystem,
    EcosystemDirectories,
)


def make_ecosystem():
    return CompEcosystem(SimpleNamespace(name="git-server"), None, None, None)


def make_root(tmp_path, names):
    for name in names:
        (tmp_path / name).mkdir()
    return EcosystemDirectories(tmp_path, None)


def test_documents_outside_the_catalog_are_not_discovered(tmp_path, monkeypatch):
    directories = make_root(tmp_path, ["jejune_doc_Listed", "jejune_doc_Unlisted"])
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        "documents:\n  - name: jejune_doc_Listed\n    url: https://example.org/x\n"
    )
    monkeypatch.setenv("JEJUNE_CATALOG", str(catalog))

    discovered = make_ecosystem().discover_doc_repos(directories)

    assert [name for name, _, _, _ in discovered] == ["jejune_doc_Listed"]


def test_without_catalog_every_document_is_discovered(tmp_path, monkeypatch):
    directories = make_root(tmp_path, ["jejune_doc_A", "jejune_doc_B"])
    monkeypatch.setenv("JEJUNE_CATALOG", str(tmp_path / "missing.yaml"))

    discovered = make_ecosystem().discover_doc_repos(directories)

    assert [name for name, _, _, _ in discovered] == ["jejune_doc_A", "jejune_doc_B"]
