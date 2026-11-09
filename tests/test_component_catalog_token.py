from jejune_cli.component_catalog import CompCatalog
from jejune_cli.component_catalog_document import CatalogDocument


def test_catalog_entry_accepts_token_file_and_rejects_other_types():
    entry = {"name": "jejune_doc_X", "url": "https://h/x.git", "public": False}
    assert CatalogDocument.validate_mapping({**entry, "token_file": "~/key"}, 0) == []
    assert CatalogDocument.validate_mapping({**entry, "token_file": 3}, 0)


def test_private_repositories_lists_token_files(tmp_path):
    catalog_file = tmp_path / "catalog.yaml"
    catalog_file.write_text(
        "documents:\n"
        "  - {name: a, url: https://h/a.git, public: true}\n"
        "  - {name: b, url: https://h/b.git, public: false, token_file: ~/key}\n"
        "  - {name: c, url: https://h/c.git, public: false}\n"
    )
    catalog = CompCatalog.__new__(CompCatalog)
    assert catalog.private_repositories(catalog_file) == [
        ("https://h/b.git", "~/key"),
        ("https://h/c.git", None),
    ]
